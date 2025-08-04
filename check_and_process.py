import os
import json
import csv
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

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


def load_original_data(csv_path, batch_size):
    """Load original data with description_id mapping."""
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # Skip header row

        # Store both description_id and sentence
        data_rows = []
        for row in reader:
            if len(row) > 1 and row[1].strip():
                description_id = row[0].strip()
                sentence = row[1].strip()
                data_rows.append((description_id, sentence))

    # Create mapping: custom_id -> list of (description_id, sentence) tuples
    mapping = {}
    for i in range(0, len(data_rows), batch_size):
        batch_data = data_rows[i:i + batch_size]
        custom_id = f"batch-{i // batch_size + 1:04d}"
        mapping[custom_id] = batch_data

    return mapping


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


def parse_output_jsonl(output_jsonl_path):
    """Returns dict custom_id -> assistant content (raw string)."""
    results = {}
    error_count = 0

    with open(output_jsonl_path, encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
                cid = item.get("custom_id")
                print(f"[DEBUG] Processing line {line_num}, custom_id: {cid}")

                # Check for actual errors - only if error field exists AND has meaningful content
                if "error" in item and item["error"] is not None and item[
                        "error"]:
                    print(
                        f"Error in line {line_num}, custom_id {cid}: {item['error']}"
                    )
                    results[cid] = None
                    error_count += 1
                    continue

                # Check if response structure exists
                if "response" not in item:
                    print(
                        f"No response field in line {line_num}, custom_id {cid}"
                    )
                    results[cid] = None
                    error_count += 1
                    continue

                response = item["response"]

                # Check if it's an HTTP error response
                if "status_code" in response and response["status_code"] != 200:
                    print(
                        f"HTTP error in line {line_num}, custom_id {cid}: {response.get('status_code')}"
                    )
                    results[cid] = None
                    error_count += 1
                    continue

                # Extract content from successful response
                try:
                    content = response["body"]["choices"][0]["message"][
                        "content"]
                    results[cid] = content
                    print(
                        f"[DEBUG] Extracted content for {cid}: {content[:100]}..."
                    )
                except KeyError as e:
                    print(
                        f"Error extracting content from line {line_num}, custom_id {cid}: Missing key {e}"
                    )
                    results[cid] = None
                    error_count += 1
                    continue

            except Exception as e:
                print(f"Error parsing line {line_num}: {e}")
                error_count += 1
                continue

    print(f"Parsed {len(results)} results with {error_count} errors")
    return results


def split_translations_with_debug(translated_blob, custom_id):
    """Enhanced version with detailed debugging."""
    if not translated_blob:
        print(f"[DEBUG] {custom_id}: Empty translation blob")
        return []

    print(f"\n[DEBUG] {custom_id}: Processing translation blob")
    print(
        f"[DEBUG] {custom_id}: Raw blob length: {len(translated_blob)} chars")
    print(
        f"[DEBUG] {custom_id}: First 200 chars: {repr(translated_blob[:200])}")

    lines = [l.strip() for l in translated_blob.splitlines() if l.strip()]
    print(f"[DEBUG] {custom_id}: Found {len(lines)} non-empty lines")

    cleaned = []
    for i, line in enumerate(lines):
        print(f"[DEBUG] {custom_id}: Line {i+1}: {repr(line[:100])}")

        # Check if line starts with a number
        if line and line[0].isdigit():
            import re
            # Try to extract the number and check if it's sequential
            match = re.match(r'^(\d+)\.\s*(.*)', line)
            if match:
                number = int(match.group(1))
                translation = match.group(2)
                print(
                    f"[DEBUG] {custom_id}: Extracted number {number}: {repr(translation[:50])}"
                )
                cleaned.append(translation)
            else:
                print(
                    f"[DEBUG] {custom_id}: Could not parse numbered line: {repr(line[:100])}"
                )
                # Try alternative patterns
                cleaned_line = re.sub(r'^\d+\.\s*', '', line)
                cleaned.append(cleaned_line)
        else:
            print(
                f"[DEBUG] {custom_id}: Non-numbered line: {repr(line[:100])}")
            cleaned.append(line)

    print(f"[DEBUG] {custom_id}: Final cleaned translations: {len(cleaned)}")
    return cleaned


def assemble_csv_with_enhanced_debug(original_mapping, model_outputs,
                                     out_csv_path):
    """Enhanced version with detailed debugging for length mismatches."""
    print(f"[+] Assembling final CSV: {out_csv_path}")
    print(f"[+] Found {len(original_mapping)} batches in original mapping")
    print(f"[+] Found {len(model_outputs)} results from model")

    successful_translations = 0
    failed_translations = 0
    mismatch_batches = []

    # Use UTF-8 encoding with BOM for better Excel compatibility
    with open(out_csv_path, "w", newline="", encoding="utf-8-sig") as csvf:
        writer = csv.writer(csvf)
        writer.writerow(
            ["description_id", "english_sentence", "telugu_sentence"])

        for custom_id, data_list in original_mapping.items():
            print(
                f"\n[DEBUG] Processing {custom_id} with {len(data_list)} entries"
            )

            # Show first few English sentences for context
            for i, (desc_id, eng_sentence) in enumerate(data_list[:3]):
                print(
                    f"[DEBUG] {custom_id}: English {i+1}: {desc_id} -> {eng_sentence[:60]}..."
                )
            if len(data_list) > 3:
                print(
                    f"[DEBUG] {custom_id}: ... and {len(data_list) - 3} more")

            telugu_blob = model_outputs.get(custom_id)

            if telugu_blob is None:
                print(f"[WARNING] No translation found for {custom_id}")
                # Missing translation: write with failure markers
                for description_id, english_sentence in data_list:
                    writer.writerow([
                        description_id, english_sentence,
                        "[TRANSLATION_FAILED]"
                    ])
                    failed_translations += 1
                continue

            print(f"[DEBUG] Found translation blob for {custom_id}")
            telugu_list = split_translations_with_debug(telugu_blob, custom_id)

            # Handle length mismatches with detailed analysis
            if len(telugu_list) != len(data_list):
                print(f"\n[ERROR] Length mismatch in {custom_id}!")
                print(f"[ERROR] Expected: {len(data_list)} English sentences")
                print(f"[ERROR] Got: {len(telugu_list)} Telugu translations")

                mismatch_batches.append({
                    'custom_id':
                    custom_id,
                    'expected':
                    len(data_list),
                    'got':
                    len(telugu_list),
                    'english_sentences': [eng for _, eng in data_list],
                    'telugu_translations':
                    telugu_list
                })

                # Save detailed debug file for this batch
                debug_filename = f"debug_{custom_id}_mismatch.txt"
                with open(debug_filename, 'w', encoding='utf-8') as debug_file:
                    debug_file.write(f"MISMATCH ANALYSIS FOR {custom_id}\n")
                    debug_file.write("=" * 50 + "\n\n")

                    debug_file.write(
                        f"Expected: {len(data_list)} translations\n")
                    debug_file.write(
                        f"Got: {len(telugu_list)} translations\n\n")

                    debug_file.write("ENGLISH SENTENCES:\n")
                    debug_file.write("-" * 30 + "\n")
                    for i, (desc_id, eng_sentence) in enumerate(data_list, 1):
                        debug_file.write(f"{i}. [{desc_id}] {eng_sentence}\n")

                    debug_file.write(f"\nTELUGU TRANSLATIONS:\n")
                    debug_file.write("-" * 30 + "\n")
                    for i, tel_sentence in enumerate(telugu_list, 1):
                        debug_file.write(f"{i}. {tel_sentence}\n")

                    debug_file.write(f"\nRAW TRANSLATION BLOB:\n")
                    debug_file.write("-" * 30 + "\n")
                    debug_file.write(telugu_blob)

                print(f"[DEBUG] Saved detailed analysis to: {debug_filename}")

                # Show side-by-side comparison
                print(f"\n[DEBUG] Side-by-side comparison for {custom_id}:")
                max_len = max(len(data_list), len(telugu_list))
                for i in range(max_len):
                    eng_text = f"[{data_list[i][0]}] {data_list[i][1][:60]}..." if i < len(
                        data_list) else "MISSING"
                    tel_text = telugu_list[i][:60] + "..." if i < len(
                        telugu_list) else "MISSING"

                    status = "✓" if i < len(data_list) and i < len(
                        telugu_list) else "✗"
                    print(f"  {status} {i+1:3d}: ENG: {eng_text}")
                    print(f"      {' '*3}  TEL: {tel_text}")

            # Pair data with translations
            for idx, (description_id,
                      english_sentence) in enumerate(data_list):
                telugu_sentence = telugu_list[idx] if idx < len(
                    telugu_list) else "[INCOMPLETE_TRANSLATION]"
                writer.writerow(
                    [description_id, english_sentence, telugu_sentence])

                if telugu_sentence and not telugu_sentence.startswith(
                        "[") and telugu_sentence.strip():
                    successful_translations += 1
                else:
                    failed_translations += 1

    print(
        f"\n[+] CSV written: {successful_translations} successful, {failed_translations} failed translations"
    )

    # Summary of mismatches
    if mismatch_batches:
        print(
            f"\n[SUMMARY] Found {len(mismatch_batches)} batches with length mismatches:"
        )
        for batch in mismatch_batches:
            print(
                f"  - {batch['custom_id']}: expected {batch['expected']}, got {batch['got']}"
            )
    else:
        print(f"\n[SUMMARY] No length mismatches found!")


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
    original_mapping = load_original_data(original_csv, batch_size)

    if custom_id not in original_mapping:
        print(f"[ERROR] Custom ID {custom_id} not found in original mapping")
        return

    # Load model outputs
    model_outputs = parse_output_jsonl(batch_output_jsonl)

    if custom_id not in model_outputs:
        print(f"[ERROR] Custom ID {custom_id} not found in model outputs")
        return

    # Analyze this specific batch
    data_list = original_mapping[custom_id]
    telugu_blob = model_outputs[custom_id]

    print(f"[DEBUG] English sentences: {len(data_list)}")
    print(f"[DEBUG] Translation blob length: {len(telugu_blob)} chars")

    telugu_list = split_translations_with_debug(telugu_blob, custom_id)

    print(f"\n[DEBUG] Final comparison:")
    print(f"Expected: {len(data_list)}")
    print(f"Got: {len(telugu_list)}")


# Replace the original functions in your code with these enhanced versions:
# 1. Replace split_translations with split_translations_with_debug
# 2. Replace assemble_csv with assemble_csv_with_enhanced_debug
# 3. Add analyze_existing_jsonl call before processing

# Example usage:
# analyze_existing_jsonl("batch_output.jsonl")
# debug_specific_batch("batch-0025", INPUT_CSV, "batch_output.jsonl", BATCH_SIZE)


def main():
    import sys

    if len(sys.argv) < 2:
        print("Usage:")
        print(
            "  python check_and_process.py <job_id>                    # Check job status"
        )
        print(
            "  python check_and_process.py <job_id> --process          # Check status and process if complete"
        )
        print(
            "  python check_and_process.py --process-local             # Process existing batch_output.jsonl"
        )
        return

    if sys.argv[1] == "--process-local":
        # Process existing local files
        if not Path("batch_output.jsonl").exists():
            print("Error: batch_output.jsonl not found")
            return

        original_mapping = load_original_data(INPUT_CSV, BATCH_SIZE)
        model_outputs = parse_output_jsonl("batch_output.jsonl")
        # Add this line before assemble_csv call
        analyze_existing_jsonl("batch_output.jsonl")
        model_outputs = parse_output_jsonl("batch_output.jsonl")
        assemble_csv_with_enhanced_debug(original_mapping, model_outputs, OUTPUT_CSV)  # Use enhanced version
        print(f"[+] Done. Final translations in: {OUTPUT_CSV}")
        return

    job_id = sys.argv[1]
    should_process = len(sys.argv) > 2 and sys.argv[2] == "--process"

    # Check job status
    job = check_job_status(job_id)
    if not job:
        return

    if job.status == "completed":
        print("[+] Job completed!")

        if should_process:
            # Download and process results
            if download_file(job.output_file_id, "batch_output.jsonl"):

                # Download errors if they exist
                if hasattr(job, 'error_file_id') and job.error_file_id:
                    download_file(job.error_file_id, "batch_errors.jsonl")
                    print("[!] Some errors occurred. Check batch_errors.jsonl")

                # Process results
                original_mapping = load_original_data(INPUT_CSV, BATCH_SIZE)
                model_outputs = parse_output_jsonl("batch_output.jsonl")
                # Add this line before assemble_csv call
                analyze_existing_jsonl("batch_output.jsonl")
                model_outputs = parse_output_jsonl("batch_output.jsonl")
                assemble_csv_with_enhanced_debug(original_mapping, model_outputs, OUTPUT_CSV)  # Use enhanced version
                print(f"[+] Done. Final translations in: {OUTPUT_CSV}")
            else:
                print("Failed to download results")
        else:
            print("Add --process flag to download and process results")

    elif job.status == "failed":
        print("[!] Job failed!")
        if hasattr(job, 'error_file_id') and job.error_file_id:
            download_file(job.error_id, "batch_errors.jsonl")
            print("Check batch_errors.jsonl for details")

    else:
        print(f"Job still {job.status}. Check again later.")


if __name__ == "__main__":
    main()
