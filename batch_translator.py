import os
import time
import json
import csv
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
import re
import sys

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


def assemble_csv(original_data, batch_mapping, model_outputs, out_csv_path):
    """Create final CSV with description_id, English, Translated columns."""
    print(f"[+] Assembling final CSV: {out_csv_path}")
    with open(out_csv_path, "w", newline="", encoding="utf-8-sig") as csvf:
        writer = csv.writer(csvf)
        writer.writerow(
            ["description_id", "english_sentence", "translated_sentence"])
        # For each batch, get the description_ids and their translations
        for custom_id, description_ids in batch_mapping.items():
            translated_blob = model_outputs.get(custom_id)
            translations = split_translations_by_id(translated_blob)
            # Find the original English for each description_id
            for description_id in description_ids:
                english_sentence = next(
                    (s for did, s in original_data if did == description_id),
                    "")
                translated_sentence = translations.get(description_id,
                                                       "[TRANSLATION_FAILED]")
                writer.writerow(
                    [description_id, english_sentence, translated_sentence])
    print("[+] CSV written with description_id mapping.")


def process_folder(jsonl_folder, csv_folder, output_folder):
    """Process all JSONL files in a folder, matching to CSVs, and outputting translations."""
    jsonl_files = [
        f for f in os.listdir(jsonl_folder) if f.lower().endswith('.jsonl')
    ]
    if not jsonl_files:
        print(f"No JSONL files found in {jsonl_folder}")
        return
    for jsonl_file in jsonl_files:
        base_name = os.path.splitext(jsonl_file)[0]
        jsonl_path = os.path.join(jsonl_folder, jsonl_file)
        csv_path = os.path.join(csv_folder, base_name + '.csv')
        out_csv_path = os.path.join(output_folder,
                                    base_name + '_translated.csv')
        if not os.path.exists(csv_path):
            print(f"[!] CSV not found for {jsonl_file}, skipping.")
            continue
        print(f"\n=== Processing {jsonl_file} ===")
        # 1. Load original data
        original_data = load_original_data(csv_path)
        # 2. Get batch mapping from JSONL
        batch_mapping = batch_mapping_from_jsonl(jsonl_path)
        # 3. Upload batch file
        input_file_id = upload_batch_file(jsonl_path)
        # 4. Create batch job
        job = create_batch_job(input_file_id)
        job_id = job.id
        print(f"[+] Batch job submitted: {job_id}")
        print(f"    Status: {job.status}")
        print(f"    To check status: python check_and_process.py {job_id}")
        # 5. Wait for completion (optional: comment out for async)
        # job = poll_until_done(job_id)
        # 6. Download and parse output (manual step, or automate if desired)
        # output_jsonl_path = ...
        # model_outputs = parse_output_jsonl(output_jsonl_path)
        # 7. Assemble CSV (manual step, or automate if desired)
        # assemble_csv(original_data, batch_mapping, model_outputs, out_csv_path)
        print(f"[!] Remember to process job {job_id} when complete.")


def main():
    if len(sys.argv) == 4:
        # Single file mode
        csv_path = sys.argv[1]
        jsonl_path = sys.argv[2]
        out_csv_path = sys.argv[3]
        original_data = load_original_data(csv_path)
        batch_mapping = batch_mapping_from_jsonl(jsonl_path)
        input_file_id = upload_batch_file(jsonl_path)
        job = create_batch_job(input_file_id)
        job_id = job.id
        print(f"[+] Batch job submitted: {job_id}")
        print(f"    Status: {job.status}")
        print(f"    To check status: python check_and_process.py {job_id}")
        # Wait for completion, download, parse, and assemble as above if desired
    elif len(sys.argv) == 5 and sys.argv[1] == '--folder':
        # Folder mode
        jsonl_folder = sys.argv[2]
        csv_folder = sys.argv[3]
        output_folder = sys.argv[4]
        if not os.path.exists(output_folder):
            os.makedirs(output_folder)
        process_folder(jsonl_folder, csv_folder, output_folder)
    else:
        print("Usage:")
        print(
            "  Single file: python batch_translator.py <input_csv> <input_jsonl> <output_csv>"
        )
        print(
            "  Folder:      python batch_translator.py --folder <jsonl_folder> <csv_folder> <output_folder>"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
