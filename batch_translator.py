import os
import time
import json
import csv
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables from .env file
load_dotenv()

# === CONFIGURATION ===
INPUT_CSV = "generic-codes-symptoms - generic-codes-symptoms.csv"  # your source English sentences with description_id
BATCH_JSONL = "batch_requests.jsonl"  # the file you already created
OUTPUT_CSV = "translations.csv"  # final mapping output
POLL_INTERVAL = 300  # seconds between job status checks (5 minutes)
MODEL_ENDPOINT = "/v1/chat/completions"  # endpoint used in the batch file
MODEL_NAME = "gpt-4o"  # used in the templates (should match your jsonl)
# =====================

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


def upload_batch_file(jsonl_path):
    print(f"[+] Uploading batch file '{jsonl_path}'...")
    with open(jsonl_path, "rb") as f:
        batch_file = client.files.create(file=f, purpose="batch")
    print(f"[+] Uploaded. File ID: {batch_file.id}")
    return batch_file.id


def create_batch_job(input_file_id):
    print("[+] Creating batch job...")
    job = client.batches.create(input_file_id=input_file_id,
                                endpoint=MODEL_ENDPOINT,
                                completion_window="24h")
    print(f"[+] Batch job created. Job ID: {job.id}, status: {job.status}")
    return job


def poll_until_done(job_id):
    print("[+] Polling job status...")
    while True:
        job = client.batches.retrieve(job_id)
        status = job.status
        print(f"    status: {status}")
        if status in ("completed", "failed"):
            return job
        time.sleep(POLL_INTERVAL)


def download_file(file_id, dest_path):
    print(f"[+] Downloading file {file_id} to {dest_path}...")
    file_response = client.files.content(file_id)
    content = file_response.content
    with open(dest_path, "wb") as f:
        f.write(content)
    print("[+] Download complete.")


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


def split_translations(translated_blob):
    """Given blob like '1. xxx\\n2. yyy', returns list of translations in order."""
    if not translated_blob:
        return []
    lines = [l.strip() for l in translated_blob.splitlines() if l.strip()]
    cleaned = []
    for l in lines:
        # Remove leading numbering "1. " or "1) "
        if l and l[0].isdigit():
            import re
            cleaned_line = re.sub(r'^\d+\.\s*', '', l)
            cleaned.append(cleaned_line)
        else:
            cleaned.append(l)
    return cleaned


def assemble_csv(original_mapping, model_outputs, out_csv_path):
    """Create final CSV with description_id, English, Telugu columns."""
    print(f"[+] Assembling final CSV: {out_csv_path}")
    with open(out_csv_path, "w", newline="", encoding="utf-8-sig") as csvf:
        writer = csv.writer(csvf)
        writer.writerow(
            ["description_id", "english_sentence", "telugu_sentence"])

        for custom_id, data_list in original_mapping.items():
            telugu_blob = model_outputs.get(custom_id)

            if telugu_blob is None:
                # Missing translation: write blanks
                for description_id, english_sentence in data_list:
                    writer.writerow([
                        description_id, english_sentence,
                        "[TRANSLATION_FAILED]"
                    ])
                continue

            telugu_list = split_translations(telugu_blob)

            # Pair data with translations
            for idx, (description_id,
                      english_sentence) in enumerate(data_list):
                telugu_sentence = telugu_list[idx] if idx < len(
                    telugu_list) else "[INCOMPLETE_TRANSLATION]"
                writer.writerow(
                    [description_id, english_sentence, telugu_sentence])

    print("[+] CSV written with description_id mapping.")


def main():
    BATCH_SIZE = 50  # adjust if you used different size when making jsonl

    if not Path(INPUT_CSV).exists():
        raise FileNotFoundError(f"Input CSV '{INPUT_CSV}' not found.")
    if not Path(BATCH_JSONL).exists():
        raise FileNotFoundError(f"Batch JSONL '{BATCH_JSONL}' not found.")

    # 1. Upload batch file
    input_file_id = upload_batch_file(BATCH_JSONL)

    # 2. Create batch job
    job = create_batch_job(input_file_id)
    job_id = job.id

    print(f"\n{'='*50}")
    print(f"BATCH JOB SUBMITTED SUCCESSFULLY!")
    print(f"Job ID: {job_id}")
    print(f"Status: {job.status}")
    print(f"{'='*50}")
    print(f"\nTo check status later, run:")
    print(f"python check_and_process.py {job_id}")
    print(f"\nTo check status and process when complete:")
    print(f"python check_and_process.py {job_id} --process")
    print(f"\nBatch jobs typically take 30 minutes to several hours.")
    print(f"Check back in 1-2 hours for small batches, longer for large ones.")

    return job_id


if __name__ == "__main__":
    main()
