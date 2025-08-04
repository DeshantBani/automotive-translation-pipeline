import os
import json
import csv
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import re

# Load environment variables from .env file
load_dotenv()

# === CONFIGURATION ===
INPUT_CSV = "generic-codes-symptoms - generic-codes-symptoms.csv"
OUTPUT_CSV = "translations.csv"
BATCH_SIZE = 50  # Must match your batch creation script

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError(
        "Set your OPENAI_API_KEY environment variable before running.")


def load_original_data(csv_path):
    """Load original data with description_id mapping."""
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # Skip header row
        data_rows = []
        for row in reader:
            if len(row) > 1 and row[1].strip():
                description_id = row[0].strip()
                sentence = row[1].strip()
                data_rows.append((description_id, sentence))
    return data_rows


def batch_mapping_from_jsonl(jsonl_path):
    """Return mapping: custom_id -> list of description_ids (in order)"""
    mapping = {}
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            item = json.loads(line)
            custom_id = item.get("custom_id")
            user_content = None
            try:
                user_content = [
                    m for m in item["body"]["messages"] if m["role"] == "user"
                ][0]["content"]
            except Exception:
                pass
            if user_content:
                # Extract description_ids from the user prompt
                ids = []
                for l in user_content.splitlines():
                    m = re.match(r"^([^.]+)\. ", l)
                    if m:
                        ids.append(m.group(1))
                mapping[custom_id] = ids
    return mapping


def parse_output_jsonl(output_jsonl_path):
    """Returns dict custom_id -> assistant content (raw string)."""
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
    """Given blob like 'desc_001. xxx\ndesc_002. yyy', returns dict description_id -> translation."""
    if not translated_blob:
        return {}
    lines = [l.strip() for l in translated_blob.splitlines() if l.strip()]
    translations = {}
    for l in lines:
        m = re.match(r"^([^.]+)\.\s*(.*)$", l)
        if m:
            description_id = m.group(1)
            translation = m.group(2)
            translations[description_id] = translation
    return translations


def is_suspicious_translation(text):
    suspicious_tokens = {
        "[TRANSLATION_FAILED]", "plaintext", "text", "code", "output", "none",
        "null"
    }
    if not text or text.strip().lower() in suspicious_tokens:
        return True
    if text.strip().startswith("```") or text.strip().startswith("<"):
        return True
    # Heuristic: very short output (less than 5 chars, not a digit)
    if len(text.strip()) < 5 and not text.strip().isdigit():
        return True
    return False


def assemble_csv_with_detailed_errors(original_data, batch_mapping,
                                      model_outputs, out_csv_path):
    """Create final CSV with description_id, English, Translated columns. Report detailed errors and flag likely shifted or suspicious translations."""
    print(f"[+] Assembling final CSV: {out_csv_path}")
    with open(out_csv_path, "w", newline="", encoding="utf-8-sig") as csvf:
        writer = csv.writer(csvf)
        writer.writerow(
            ["description_id", "english_sentence", "translated_sentence"])
        all_failed = []
        all_extra = []
        all_success = 0
        all_shifted = []
        all_suspicious = []
        for custom_id, description_ids in batch_mapping.items():
            translated_blob = model_outputs.get(custom_id)
            translations = split_translations_by_id(translated_blob)
            missing = []
            extra = []
            batch_rows = []  # For shift detection
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
            # Find extra translations not in the batch
            for tid in translations:
                if tid not in description_ids:
                    extra.append((tid, translations[tid]))
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
            # Shifted translation check
            for i in range(len(batch_rows) - 1):
                curr_id, curr_eng, curr_trans = batch_rows[i]
                next_id, next_eng, next_trans = batch_rows[i + 1]
                if (curr_trans == "[TRANSLATION_FAILED]"
                        or is_suspicious_translation(curr_trans)
                    ) and next_trans not in (
                        "[TRANSLATION_FAILED]", None,
                        "") and not is_suspicious_translation(next_trans):
                    # If the next translation is not blank or suspicious, flag possible shift
                    all_shifted.append(
                        (custom_id, curr_id, curr_eng, next_id, next_trans))
            # Check if last row is blank or suspicious
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
        print(f"[SUMMARY] {all_success} successful translations written.")
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
        if not all_failed and not all_extra and not all_shifted and not all_suspicious:
            print("[SUMMARY] All translations matched by description_id.")


def check_job_status(job_id):
    """Check the status of a batch job."""
    try:
        job = client.batches.retrieve(job_id)
        print(f"Job ID: {job_id}")
        print(f"Status: {job.status}")
        print(f"Created at: {job.created_at}")
        if hasattr(job, 'completed_at') and job.completed_at:
            print(f"Completed at: {job.completed_at}")
        if hasattr(job, 'request_counts'):
            print(f"Request counts: {job.request_counts}")
        return job
    except Exception as e:
        print(f"Error checking job status: {e}")
        return None


def download_file(file_id, dest_path):
    """Download a file from OpenAI."""
    print(f"[+] Downloading file {file_id} to {dest_path}...")
    try:
        file_response = client.files.content(file_id)
        content = file_response.content
        with open(dest_path, "wb") as f:
            f.write(content)
        print("[+] Download complete.")
        return True
    except Exception as e:
        print(f"Error downloading file: {e}")
        return False


def analyze_existing_jsonl(jsonl_path):
    """Analyze the batch_output.jsonl to identify potential issues."""
    print(f"\n[ANALYSIS] Analyzing {jsonl_path}")

    with open(jsonl_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            try:
                item = json.loads(line)
                custom_id = item.get("custom_id")

                # Check for errors
                if "error" in item and item["error"]:
                    print(
                        f"[ERROR] Line {line_num} ({custom_id}): {item['error']}"
                    )
                    continue

                # Extract content
                try:
                    content = item["response"]["body"]["choices"][0][
                        "message"]["content"]

                    # Analyze the content
                    lines = [
                        l.strip() for l in content.splitlines() if l.strip()
                    ]
                    numbered_lines = [l for l in lines if l and l[0].isdigit()]

                    print(
                        f"[INFO] {custom_id}: {len(lines)} total lines, {len(numbered_lines)} numbered"
                    )

                    # Check for potential issues
                    if len(numbered_lines) != len(lines):
                        print(f"[WARNING] {custom_id}: Has non-numbered lines")

                    # Check numbering sequence
                    numbers = []
                    for line in numbered_lines:
                        import re
                        match = re.match(r'^(\d+)\.', line)
                        if match:
                            numbers.append(int(match.group(1)))

                    if numbers:
                        expected = list(range(1, len(numbers) + 1))
                        if numbers != expected:
                            print(
                                f"[WARNING] {custom_id}: Numbering issue - got {numbers[:10]}..., expected {expected[:10]}..."
                            )

                except KeyError as e:
                    print(
                        f"[ERROR] Line {line_num} ({custom_id}): Missing key {e}"
                    )

            except json.JSONDecodeError as e:
                print(f"[ERROR] Line {line_num}: JSON decode error - {e}")


# Usage functions
def debug_specific_batch(custom_id,
                         original_csv,
                         batch_output_jsonl,
                         batch_size=50):
    """Debug a specific batch by custom_id."""
    print(f"\n[DEBUG] Analyzing specific batch: {custom_id}")

    # Load original mapping
    original_data = load_original_data(original_csv)

    # Load batch mapping from the JSONL used to create the batch
    print(
        "[INFO] Please provide the JSONL used to create the batch for accurate mapping."
    )
    batch_jsonl_path = input("Enter path to the batch JSONL file: ").strip()
    batch_mapping = batch_mapping_from_jsonl(batch_jsonl_path)

    if custom_id not in batch_mapping:
        print(f"[ERROR] Custom ID {custom_id} not found in batch mapping")
        return

    # Load model outputs
    model_outputs = parse_output_jsonl(batch_output_jsonl)

    if custom_id not in model_outputs:
        print(f"[ERROR] Custom ID {custom_id} not found in model outputs")
        return

    # Analyze this specific batch
    description_ids = batch_mapping[custom_id]
    missing_ids = []
    extra_ids = []
    for description_id in description_ids:
        english_sentence = next(
            (s for did, s in original_data if did == description_id), "")
        translated_sentence = model_outputs[custom_id]
        if translated_sentence is None:
            missing_ids.append((description_id, english_sentence))
        else:
            translations = split_translations_by_id(translated_sentence)
            if description_id not in translations:
                extra_ids.append((description_id, english_sentence))

    print(f"[DEBUG] English sentences: {len(description_ids)}")
    print(f"[DEBUG] Translation blob length: {len(translated_sentence)} chars")

    print(f"\n[DEBUG] Missing translations for {custom_id}:")
    for did, eng in missing_ids:
        print(f"  - {did}: {eng}")

    print(f"\n[DEBUG] Extra translations for {custom_id}:")
    for did, eng in extra_ids:
        print(f"  - {did}: {eng}")


# Replace the original functions in your code with these enhanced versions:
# 1. Replace split_translations with split_translations_with_debug
# 2. Replace assemble_csv with assemble_csv_with_enhanced_debug
# 3. Add analyze_existing_jsonl call before processing

# Example usage:
# analyze_existing_jsonl("batch_output.jsonl")
# debug_specific_batch("batch-0025", INPUT_CSV, "batch_output.jsonl", BATCH_SIZE)


def main():
    import sys
    if len(sys.argv) < 4:
        print(
            "Usage: python check_and_process.py <input_csv> <batch_output.jsonl> <output_csv>"
        )
        print(
            "Example: python check_and_process.py test_input.csv batch_output.jsonl translations.csv"
        )
        return
    input_csv = sys.argv[1]
    batch_output_jsonl = sys.argv[2]
    output_csv = sys.argv[3]
    original_data = load_original_data(input_csv)
    # Load batch mapping from the JSONL used to create the batch
    print(
        "[INFO] Please provide the JSONL used to create the batch for accurate mapping."
    )
    batch_jsonl_path = input("Enter path to the batch JSONL file: ").strip()
    batch_mapping = batch_mapping_from_jsonl(batch_jsonl_path)
    model_outputs = parse_output_jsonl(batch_output_jsonl)
    assemble_csv_with_detailed_errors(original_data, batch_mapping,
                                      model_outputs, output_csv)
    print(f"[+] Done. Final translations in: {output_csv}")


if __name__ == "__main__":
    main()
