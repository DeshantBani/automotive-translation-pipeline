#!/usr/bin/env python3
"""
Automated End-to-End Translation Pipeline
Handles everything from CSV input to final translations without manual intervention.
"""

import os
import sys
import time
import json
import csv
import re
import tiktoken
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import tiktoken

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError(
        "Set your OPENAI_API_KEY environment variable before running.")

# Configuration
MODEL_NAME = "gpt-4o"
MODEL_TOKEN_LIMIT = 8000  # Reduced from 16000 for smaller batches
EXPECTED_OUTPUT_FACTOR = 1.2  # Increased to account for tuple format
POLL_INTERVAL = 300  # 5 minutes


def get_system_prompt(target_language):
    return f"""You are an expert automotive translator proficient in English and {target_language}. Your task is to translate technical automotive sentences from English into accurate, formal {target_language}.

CRITICAL INSTRUCTIONS:
1. You will receive a JSON object where each key is a description_id and each value is an English sentence
2. You MUST return a JSON object with the EXACT same keys (description_ids) mapped to their {target_language} translations
3. Preserve the exact description_id mapping - do not change, reorder, or skip any IDs
4. Ensure technical automotive terminology is translated precisely
5. If a technical term doesn't have an exact {target_language} equivalent, retain it in English or transliterate it clearly
6. Preserve numeric codes (e.g., P0089) as-is

INPUT FORMAT: {{"id1": "sentence1", "id2": "sentence2", ...}}
OUTPUT FORMAT: {{"id1": "translation1", "id2": "translation2", ...}}

Example:
Input: {{"21": "Low fuel pressure detected", "27": "Engine misfire detected"}}
Output: {{"21": "<{target_language} translation>", "27": "<{target_language} translation>"}}

IMPORTANT: Return ONLY the JSON object with translations. No explanations, no additional text."""


def count_tokens(text, encoding):
    return len(encoding.encode(text))


def create_jsonl_from_csv(csv_filename, jsonl_filename, target_language):
    """Create JSONL file from CSV with smaller batches and JSON format for better mapping."""
    encoding = tiktoken.encoding_for_model(MODEL_NAME)

    with open(csv_filename, 'r', encoding='utf-8') as csv_file:
        reader = csv.reader(csv_file)
        next(reader)  # Skip the header row
        data_rows = []
        for row in reader:
            if len(row) > 1 and row[1].strip():
                description_id = row[0].strip()
                sentence = row[1].strip()
                data_rows.append((description_id, sentence))

    system_prompt = get_system_prompt(target_language)
    system_prompt_tokens = count_tokens(system_prompt, encoding)

    batches = []
    current_batch = []
    current_tokens = system_prompt_tokens

    for (description_id, sentence) in data_rows:
        # Create JSON format: {"id": "sentence"}
        json_entry = {description_id: sentence}
        json_str = json.dumps(json_entry, ensure_ascii=False)
        line_tokens = count_tokens(json_str, encoding)
        est_output_tokens = int(line_tokens * EXPECTED_OUTPUT_FACTOR)
        total_if_added = current_tokens + line_tokens + est_output_tokens

        if total_if_added > MODEL_TOKEN_LIMIT and current_batch:
            batches.append(current_batch)
            current_batch = []
            current_tokens = system_prompt_tokens

        current_batch.append((description_id, sentence))
        current_tokens += line_tokens + est_output_tokens

    if current_batch:
        batches.append(current_batch)

    with open(jsonl_filename, 'w', encoding='utf-8') as jsonl_file:
        for batch_num, batch_data in enumerate(batches, 1):
            # Create JSON object for the batch
            batch_json = {}
            for description_id, sentence in batch_data:
                batch_json[description_id] = sentence

            json_entry = {
                "custom_id": f"batch-{batch_num:04d}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model":
                    MODEL_NAME,
                    "messages": [{
                        "role": "system",
                        "content": system_prompt
                    }, {
                        "role":
                        "user",
                        "content":
                        json.dumps(batch_json, ensure_ascii=False)
                    }],
                    "temperature":
                    0,
                    "max_tokens":
                    MODEL_TOKEN_LIMIT
                }
            }
            jsonl_file.write(json.dumps(json_entry, ensure_ascii=False) + '\n')

    print(
        f"Created JSONL file with {len(data_rows)} sentences across {len(batches)} batches"
    )
    print(
        f"Average batch size: {len(data_rows)/len(batches):.1f} sentences per batch"
    )
    return batches


def upload_batch_file(jsonl_path):
    """Upload batch file to OpenAI."""
    print(f"Uploading batch file '{jsonl_path}'...")
    with open(jsonl_path, "rb") as f:
        batch_file = client.files.create(file=f, purpose="batch")
    print(f"Uploaded. File ID: {batch_file.id}")
    return batch_file.id


def create_batch_job(input_file_id):
    """Create batch job."""
    print("Creating batch job...")
    job = client.batches.create(input_file_id=input_file_id,
                                endpoint="/v1/chat/completions",
                                completion_window="24h")
    print(f"Batch job created. Job ID: {job.id}, status: {job.status}")
    return job


def poll_until_done(job_id):
    """Poll job until completion."""
    print("Polling job status...")
    while True:
        job = client.batches.retrieve(job_id)
        status = job.status
        print(f"Status: {status}")

        if status in ("completed", "failed"):
            return job

        print(f"Job still {status}. Waiting {POLL_INTERVAL} seconds...")
        time.sleep(POLL_INTERVAL)


def download_file(file_id, dest_path):
    """Download file from OpenAI."""
    print(f"Downloading file {file_id} to {dest_path}...")
    try:
        file_response = client.files.content(file_id)
        content = file_response.content
        with open(dest_path, "wb") as f:
            f.write(content)
        print("Download complete.")
        return True
    except Exception as e:
        print(f"Error downloading file: {e}")
        return False


def parse_output_jsonl(output_jsonl_path):
    """Parse output JSONL and return custom_id -> content mapping."""
    results = {}
    with open(output_jsonl_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            cid = item.get("custom_id")
            try:
                content = item["response"]["body"]["choices"][0]["message"][
                    "content"]
            except Exception:
                content = None
            results[cid] = content
    return results


def split_translations_by_id(translated_blob):
    """Extract translations by description_id from JSON format."""
    if not translated_blob:
        return {}

    translations = {}

    try:
        # Clean the blob to extract JSON from markdown code blocks
        cleaned_blob = translated_blob.strip()

        # Remove markdown code block markers
        if cleaned_blob.startswith('```json'):
            cleaned_blob = cleaned_blob[7:]  # Remove ```json
        elif cleaned_blob.startswith('```'):
            cleaned_blob = cleaned_blob[3:]  # Remove ```

        if cleaned_blob.endswith('```'):
            cleaned_blob = cleaned_blob[:-3]  # Remove closing ```

        cleaned_blob = cleaned_blob.strip()

        # First try to parse as JSON (new format)
        json_data = json.loads(cleaned_blob)
        if isinstance(json_data, dict):
            # Direct JSON mapping - this is what we want
            for desc_id, translation in json_data.items():
                if translation and str(translation).strip():
                    translations[str(desc_id)] = str(translation).strip()
            return translations
    except json.JSONDecodeError as e:
        print(f"JSON decode error for batch response: {e}")
        print(f"First 200 chars of response: {translated_blob[:200]}...")
        # If JSON parsing fails, fall back to line-by-line parsing
        pass

    # Fallback: Parse line by line (for backward compatibility)
    lines = [l.strip() for l in translated_blob.splitlines() if l.strip()]

    for l in lines:
        # Skip code blocks and other non-translation content
        if l.startswith('```') or l.startswith('<') or l in [
                'plaintext', 'json', 'text'
        ]:
            continue

        # Try multiple patterns to handle different output formats
        patterns = [
            # Pattern 1: JSON-like "id": "translation"
            r'^"?(\d+)"?\s*:\s*"(.+?)"$',
            # Pattern 2: "277. ('597', 'translation')" - tuple format (handle first)
            r"^(\d+)\.\s*\(\'(\d+)\',\s*\'(.+?)\'\)$",
            # Pattern 3: "desc_021. translation" or "21. translation"
            r"^(?:desc_)?(\d+)\.\s*(.*)$",
            # Pattern 4: Generic "key. value" format
            r"^([^.]+)\.\s*(.*)$"
        ]

        matched = False
        for pattern in patterns:
            m = re.match(pattern, l)
            if m:
                if len(m.groups()) == 2:
                    # Standard format
                    description_id = m.group(1)
                    translation = m.group(2)
                elif len(m.groups()) == 3:
                    # Tuple format: use the ID from inside the tuple
                    description_id = m.group(2)
                    translation = m.group(3)

                # Clean up description_id (remove 'desc_' prefix if present)
                if description_id.startswith('desc_'):
                    description_id = description_id[5:]

                # Clean up translation (remove quotes if present)
                translation = translation.strip().strip('"').strip("'")

                # Only add if translation is not empty and not suspicious
                if translation and not is_suspicious_translation(translation):
                    translations[description_id] = translation
                matched = True
                break

        # Debug: print unmatched lines for troubleshooting
        if not matched and l and len(translations) < 10:
            print(f"Warning: Could not parse line: {l[:100]}...")

    return translations


def is_suspicious_translation(text):
    """Check if translation is suspicious."""
    if not text or not isinstance(text, str):
        return True

    text_lower = text.strip().lower()
    suspicious_tokens = {
        "[translation_failed]", "plaintext", "text", "code", "output", "none",
        "null", "undefined", "error", "failed", "missing", "empty", "json",
        "translation", "response", "content", "message", "system", "user"
    }

    if text_lower in suspicious_tokens:
        return True
    if text.strip().startswith("```") or text.strip().startswith("<"):
        return True
    if text.strip().startswith("{") or text.strip().startswith("["):
        return True
    if len(text.strip()) < 3:  # Very short translations are suspicious
        return True
    if text.strip().isdigit():  # Pure numbers are suspicious
        return True

    return False


def process_results(input_csv, output_jsonl, final_csv, batches):
    """Process batch results and create final CSV."""
    print(f"Processing results...")

    # Load original data
    with open(input_csv, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)
        original_data = []
        for row in reader:
            if len(row) > 1 and row[1].strip():
                description_id = row[0].strip()
                sentence = row[1].strip()
                original_data.append((description_id, sentence))

    # Parse model outputs
    model_outputs = parse_output_jsonl(output_jsonl)
    print(f"Found {len(model_outputs)} batch responses")

    # Create batch mapping
    batch_mapping = {}
    for i, batch_data in enumerate(batches, 1):
        custom_id = f"batch-{i:04d}"
        description_ids = [desc_id for desc_id, _ in batch_data]
        batch_mapping[custom_id] = description_ids

    # Write final CSV
    with open(final_csv, "w", newline="", encoding="utf-8-sig") as csvf:
        writer = csv.writer(csvf)
        writer.writerow(
            ["description_id", "english_sentence", "translated_sentence"])

        all_failed = []
        all_extra = []
        all_success = 0
        all_shifted = []
        all_suspicious = []

        for custom_id, description_ids in batch_mapping.items():
            print(f"Processing {custom_id}...")
            translated_blob = model_outputs.get(custom_id)
            translations = split_translations_by_id(translated_blob)
            print(f"  Extracted {len(translations)} translations")
            missing = []
            extra = []
            batch_rows = []

            for description_id in description_ids:
                english_sentence = next(
                    (s for did, s in original_data if did == description_id),
                    "")
                translated_sentence = translations.get(description_id)

                if translated_sentence is None:
                    writer.writerow([
                        description_id, english_sentence,
                        "[TRANSLATION_FAILED]"
                    ])
                    missing.append((description_id, english_sentence))
                    batch_rows.append((description_id, english_sentence,
                                       "[TRANSLATION_FAILED]"))
                else:
                    writer.writerow([
                        description_id, english_sentence, translated_sentence
                    ])
                    all_success += 1
                    batch_rows.append((description_id, english_sentence,
                                       translated_sentence))

                    if is_suspicious_translation(translated_sentence):
                        all_suspicious.append(
                            (custom_id, description_id, english_sentence,
                             translated_sentence))

            # Find extra translations
            for tid in translations:
                if tid not in description_ids:
                    extra.append((tid, translations[tid]))

            # Shift detection
            for i in range(len(batch_rows) - 1):
                curr_id, curr_eng, curr_trans = batch_rows[i]
                next_id, next_eng, next_trans = batch_rows[i + 1]
                if (curr_trans == "[TRANSLATION_FAILED]"
                        or is_suspicious_translation(curr_trans)
                    ) and next_trans not in (
                        "[TRANSLATION_FAILED]", None,
                        "") and not is_suspicious_translation(next_trans):
                    all_shifted.append(
                        (custom_id, curr_id, curr_eng, next_id, next_trans))

            if batch_rows and (batch_rows[-1][2] == "[TRANSLATION_FAILED]"
                               or is_suspicious_translation(
                                   batch_rows[-1][2])) and len(batch_rows) > 1:
                prev_id, prev_eng, prev_trans = batch_rows[-2]
                if prev_trans not in (
                        "[TRANSLATION_FAILED]", None,
                        "") and not is_suspicious_translation(prev_trans):
                    all_shifted.append(
                        (custom_id, batch_rows[-1][0], batch_rows[-1][1],
                         prev_id, prev_trans))

            if missing:
                print(f"[ERROR] Batch {custom_id}: Missing translations for:")
                for did, eng in missing:
                    print(f"  - {did}: {eng}")
                all_failed.extend([(custom_id, did, eng)
                                   for did, eng in missing])

            if extra:
                print(
                    f"[WARNING] Batch {custom_id}: Extra translations returned:"
                )
                for tid, tval in extra:
                    print(f"  - {tid}: {tval}")
                all_extra.extend([(custom_id, tid, tval)
                                  for tid, tval in extra])

    # Print summary
    total_processed = len(original_data)
    print(f"\n=== TRANSLATION RESULTS ===")
    print(f"Successful translations: {all_success}")
    print(f"Failed translations: {len(all_failed)}")
    print(f"Total processed: {total_processed}")
    if total_processed > 0:
        print(f"Success rate: {all_success/total_processed*100:.1f}%")
    print(f"Final output: {final_csv}")

    print(
        f"\n[SUMMARY] {all_success} successful translations written to {final_csv}"
    )

    if all_failed:
        print(f"[SUMMARY] {len(all_failed)} missing translations:")
        for custom_id, did, eng in all_failed:
            print(f"  - Batch {custom_id}, {did}: {eng}")

    if all_extra:
        print(f"[SUMMARY] {len(all_extra)} extra translations returned:")
        for custom_id, tid, tval in all_extra:
            print(f"  - Batch {custom_id}, {tid}: {tval}")

    if all_suspicious:
        print(
            f"[SUSPICIOUS] {len(all_suspicious)} suspicious translations detected:"
        )
        for custom_id, did, eng, trans in all_suspicious:
            print(
                f"  - Batch {custom_id}, {did}: '{trans}' (English: '{eng[:40]}...')"
            )

    if all_shifted:
        print(
            f"[SHIFT WARNING] {len(all_shifted)} possible shifted translations detected:"
        )
        for custom_id, missing_id, missing_eng, shifted_from_id, shifted_trans in all_shifted:
            print(
                f"  - Batch {custom_id}: Likely translation for {missing_id} ('{missing_eng[:40]}...') was output for {shifted_from_id}: '{shifted_trans[:40]}...'"
            )

    # Final status message
    if not all_failed and not all_extra and not all_shifted and not all_suspicious:
        print(
            f"\n🎉 SUCCESS: All {all_success} translations completed perfectly!"
        )
        print("[SUMMARY] All translations matched by description_id.")
    else:
        print(
            f"\n⚠️  COMPLETED WITH ISSUES: {all_success} successful, {len(all_failed)} failed"
        )
        if all_extra:
            print(f"   - {len(all_extra)} extra translations")
        if all_shifted:
            print(f"   - {len(all_shifted)} shifted translations")
        if all_suspicious:
            print(f"   - {len(all_suspicious)} suspicious translations")


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python auto_translate.py <input_csv> <target_language> <output_csv>"
        )
        print(
            "Example: python auto_translate.py test_input.csv Hindi translations.csv"
        )
        sys.exit(1)

    input_csv = sys.argv[1]
    target_language = sys.argv[2]
    output_csv = sys.argv[3]

    # Create unique file names based on input file
    input_stem = Path(input_csv).stem
    timestamp = int(time.time())
    unique_id = f"{input_stem}_{timestamp}"

    # Unique file names
    jsonl_file = f"{unique_id}_batch.jsonl"
    output_jsonl = f"{unique_id}_output.jsonl"
    error_jsonl = f"{unique_id}_errors.jsonl"

    # Step 1: Create JSONL from CSV
    print("=== Step 1: Creating JSONL from CSV ===")
    batches = create_jsonl_from_csv(input_csv, jsonl_file, target_language)

    # Step 2: Upload and create batch job
    print("\n=== Step 2: Uploading and creating batch job ===")
    input_file_id = upload_batch_file(jsonl_file)
    job = create_batch_job(input_file_id)
    job_id = job.id

    print(f"\n{'='*50}")
    print(f"BATCH JOB SUBMITTED SUCCESSFULLY!")
    print(f"Job ID: {job_id}")
    print(f"Status: {job.status}")
    print(f"Unique ID: {unique_id}")
    print(f"{'='*50}")

    # Step 3: Wait for completion
    print("\n=== Step 3: Waiting for job completion ===")
    job = poll_until_done(job_id)

    if job.status == "completed":
        print("\n=== Step 4: Processing results ===")

        # Download results
        if download_file(job.output_file_id, output_jsonl):
            # Download errors if they exist
            if hasattr(job, 'error_file_id') and job.error_file_id:
                download_file(job.error_file_id, error_jsonl)
                print(f"[!] Some errors occurred. Check {error_jsonl}")

            # Process results
            process_results(input_csv, output_jsonl, output_csv, batches)
            print(
                f"\n[+] Pipeline complete! Final translations in: {output_csv}"
            )
        else:
            print("Failed to download results")
    elif job.status == "failed":
        print("[!] Job failed!")
        if hasattr(job, 'error_file_id') and job.error_file_id:
            download_file(job.error_file_id, error_jsonl)
            print(f"Check {error_jsonl} for details")


if __name__ == "__main__":
    main()
