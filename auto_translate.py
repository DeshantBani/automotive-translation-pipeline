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
import logging
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI

# Load environment variables
load_dotenv()

# Initialize OpenAI client
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
if not os.getenv("OPENAI_API_KEY"):
    raise RuntimeError(
        "Set your OPENAI_API_KEY environment variable before running.")

# Configuration
MODEL_NAME = "gpt-4o"
MODEL_TOKEN_LIMIT = 4000  # Reduced from 16000 for smaller batches
EXPECTED_OUTPUT_FACTOR = 1.8  # Increased to account for tuple format
POLL_INTERVAL = 300  # 5 minutes
BATCH_TRACKING_FILE = "batch_job_tracking.csv"

# Auto-repair Configuration
AUTO_REPAIR_ENABLED = True
MAX_REPAIR_ATTEMPTS = 3
REPAIR_CONFIDENCE_THRESHOLD = 0.8
BACKUP_FAILED_BATCHES = True


def setup_logging(log_filename=None):
    """Set up logging to both console and file with timestamps."""
    if log_filename is None:
        timestamp = int(time.time())
        log_filename = f"translation_log_{timestamp}.txt"

    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)

    log_path = log_dir / log_filename

    # Configure logging format
    log_format = '%(asctime)s - %(levelname)s - %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # Remove any existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Configure logging to write to both file and console
    logging.basicConfig(level=logging.INFO,
                        format=log_format,
                        datefmt=date_format,
                        handlers=[
                            logging.FileHandler(log_path, encoding='utf-8'),
                            logging.StreamHandler(sys.stdout)
                        ])

    return str(log_path)


class DualLogger:
    """Custom logger that prints to both console and log file."""

    def __init__(self, log_path):
        self.log_path = log_path
        self.logger = logging.getLogger(__name__)

    def log(self, message, level="INFO"):
        """Log message at specified level."""
        if level == "INFO":
            self.logger.info(message)
        elif level == "ERROR":
            self.logger.error(message)
        elif level == "WARNING":
            self.logger.warning(message)
        elif level == "DEBUG":
            self.logger.debug(message)

    def info(self, message):
        """Log info message."""
        self.log(message, "INFO")

    def error(self, message):
        """Log error message."""
        self.log(message, "ERROR")

    def warning(self, message):
        """Log warning message."""
        self.log(message, "WARNING")

    def debug(self, message):
        """Log debug message."""
        self.log(message, "DEBUG")


# Global logger instance
logger = None


def initialize_batch_tracking():
    """Initialize the batch tracking CSV file if it doesn't exist."""
    if not Path(BATCH_TRACKING_FILE).exists():
        with open(BATCH_TRACKING_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                'batch_id', 'input_file', 'job_id', 'status', 'timestamp',
                'target_language', 'output_file'
            ])
        if logger:
            logger.info(
                f"Created new batch tracking file: {BATCH_TRACKING_FILE}")
        else:
            print(f"Created new batch tracking file: {BATCH_TRACKING_FILE}")
    else:
        if logger:
            logger.info(
                f"Using existing batch tracking file: {BATCH_TRACKING_FILE}")


def add_batch_record(batch_id,
                     input_file,
                     job_id,
                     status,
                     timestamp,
                     target_language,
                     output_file=None):
    """Add a new batch record to the tracking CSV file."""
    # Ensure the file exists with headers
    initialize_batch_tracking()

    # Append the new record
    with open(BATCH_TRACKING_FILE, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerow([
            batch_id, input_file, job_id, status, timestamp, target_language,
            output_file or ""
        ])

    if logger:
        logger.info(f"Added batch record: {batch_id} -> {job_id} ({status})")
    else:
        print(f"Added batch record: {batch_id} -> {job_id} ({status})")


def update_batch_status(job_id, new_status, output_file=None):
    """Update the status of an existing batch record."""
    if not Path(BATCH_TRACKING_FILE).exists():
        if logger:
            logger.warning(
                f"Batch tracking file does not exist: {BATCH_TRACKING_FILE}")
        else:
            print(
                f"Warning: Batch tracking file does not exist: {BATCH_TRACKING_FILE}"
            )
        return False

    # Read all records
    records = []
    updated = False

    with open(BATCH_TRACKING_FILE, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        records.append(header)

        for row in reader:
            if len(row) >= 3 and row[2] == job_id:  # job_id is in column 2
                # Update status (column 3) and output_file (column 6) if provided
                row[3] = new_status
                if output_file:
                    row[6] = output_file
                updated = True
                if logger:
                    logger.info(
                        f"Updated batch record: {job_id} -> {new_status}")
                else:
                    print(f"Updated batch record: {job_id} -> {new_status}")
            records.append(row)

    if updated:
        # Write back all records
        with open(BATCH_TRACKING_FILE, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerows(records)
        return True
    else:
        if logger:
            logger.warning(f"Job ID not found in tracking file: {job_id}")
        else:
            print(f"Warning: Job ID not found in tracking file: {job_id}")
        return False


def get_batch_record(job_id):
    """Get a batch record by job_id."""
    if not Path(BATCH_TRACKING_FILE).exists():
        return None

    with open(BATCH_TRACKING_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row['job_id'] == job_id:
                return row
    return None


def list_batch_records(status_filter=None):
    """List all batch records, optionally filtered by status."""
    if not Path(BATCH_TRACKING_FILE).exists():
        if logger:
            logger.info("No batch tracking file found")
        return []

    records = []
    with open(BATCH_TRACKING_FILE, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            if status_filter is None or row['status'] == status_filter:
                records.append(row)

    return records


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

    logger.info(
        f"Created JSONL file with {len(data_rows)} sentences across {len(batches)} batches"
    )
    logger.info(
        f"Average batch size: {len(data_rows)/len(batches):.1f} sentences per batch"
    )
    return batches


def upload_batch_file(jsonl_path):
    """Upload batch file to OpenAI."""
    logger.info(f"Uploading batch file '{jsonl_path}'...")
    with open(jsonl_path, "rb") as f:
        batch_file = client.files.create(file=f, purpose="batch")
    logger.info(f"Uploaded. File ID: {batch_file.id}")
    return batch_file.id


def create_batch_job(input_file_id):
    """Create batch job."""
    logger.info("Creating batch job...")
    job = client.batches.create(input_file_id=input_file_id,
                                endpoint="/v1/chat/completions",
                                completion_window="24h")
    logger.info(f"Batch job created. Job ID: {job.id}, status: {job.status}")
    return job


def poll_until_done(job_id):
    """Poll job until completion."""
    logger.info("Polling job status...")
    while True:
        job = client.batches.retrieve(job_id)
        status = job.status
        logger.info(f"Status: {status}")

        if status in ("completed", "failed"):
            return job

        logger.info(f"Job still {status}. Waiting {POLL_INTERVAL} seconds...")
        time.sleep(POLL_INTERVAL)


def download_file(file_id, dest_path):
    """Download file from OpenAI."""
    logger.info(f"Downloading file {file_id} to {dest_path}...")
    try:
        file_response = client.files.content(file_id)
        content = file_response.content
        with open(dest_path, "wb") as f:
            f.write(content)
        logger.info("Download complete.")
        return True
    except Exception as e:
        logger.error(f"Error downloading file: {e}")
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


def _cleanup_markdown_basic(blob):
    """Basic markdown cleanup - removes simple code block markers."""
    cleaned = blob.strip()

    # Remove basic markdown code block markers
    if cleaned.startswith('```json'):
        cleaned = cleaned[7:]
    elif cleaned.startswith('```'):
        cleaned = cleaned[3:]

    if cleaned.endswith('```'):
        cleaned = cleaned[:-3]

    return cleaned.strip()


def _cleanup_markdown_aggressive(blob):
    """Aggressive markdown cleanup using regex patterns."""
    import re

    # Remove all code block markers with optional language specifiers
    cleaned = re.sub(r'^```(?:json|javascript|text)?\s*\n?',
                     '',
                     blob.strip(),
                     flags=re.MULTILINE)
    cleaned = re.sub(r'\n?```\s*$', '', cleaned, flags=re.MULTILINE)

    # Remove any remaining triple backticks
    cleaned = re.sub(r'```', '', cleaned)

    return cleaned.strip()


def _cleanup_markdown_multiline(blob):
    """Handle multiline markdown with embedded newlines in code blocks."""
    import re

    # Split by lines and remove markdown markers
    lines = blob.split('\n')
    cleaned_lines = []
    in_code_block = False

    for line in lines:
        line = line.strip()
        if line.startswith('```'):
            in_code_block = not in_code_block
            continue
        if not in_code_block:
            continue
        if line:
            cleaned_lines.append(line)

    if cleaned_lines:
        return '\n'.join(cleaned_lines)

    # Fallback to basic cleanup
    return _cleanup_markdown_basic(blob)


def _cleanup_unicode_and_escapes(blob):
    """Handle Unicode escapes and special characters in JSON."""
    import re

    # First do basic markdown cleanup
    cleaned = _cleanup_markdown_basic(blob)

    # Fix common JSON formatting issues
    # Remove any leading/trailing whitespace and normalize quotes
    cleaned = re.sub(r'^\s*[\'"]*', '', cleaned)
    cleaned = re.sub(r'[\'"]*\s*$', '', cleaned)

    # Ensure proper JSON structure if it looks like it should be an object
    if not cleaned.startswith('{') and ':' in cleaned:
        cleaned = '{' + cleaned
    if not cleaned.endswith('}') and cleaned.startswith('{'):
        cleaned = cleaned + '}'

    return cleaned.strip()


def split_translations_by_id(translated_blob):
    """Enhanced extraction of translations by description_id from JSON format with robust parsing."""
    if not translated_blob:
        return {}

    translations = {}

    # Strategy 1: Enhanced JSON parsing with multiple cleanup attempts
    for strategy_num, cleanup_func in enumerate([
            _cleanup_markdown_basic, _cleanup_markdown_aggressive,
            _cleanup_markdown_multiline, _cleanup_unicode_and_escapes
    ], 1):
        try:
            cleaned_blob = cleanup_func(translated_blob)
            if not cleaned_blob:
                continue

            # Try to parse as JSON
            json_data = json.loads(cleaned_blob)
            if isinstance(json_data, dict) and json_data:
                logger.info(
                    f"Successfully parsed JSON using cleanup strategy {strategy_num}"
                )
                # Direct JSON mapping - this is what we want
                for desc_id, translation in json_data.items():
                    if translation and str(translation).strip():
                        clean_translation = str(translation).strip()
                        if not is_suspicious_translation(clean_translation):
                            translations[str(desc_id)] = clean_translation
                return translations
        except json.JSONDecodeError as e:
            if strategy_num == 1:  # Only print detailed error for first strategy
                logger.warning(
                    f"JSON decode strategy {strategy_num} failed: {e}")
                logger.debug(f"First 200 chars: {translated_blob[:200]}...")
            continue
        except Exception as e:
            logger.error(f"Unexpected error in strategy {strategy_num}: {e}")
            continue

    # Strategy 2: Enhanced fallback parsing with better error recovery
    logger.warning(
        "All JSON parsing strategies failed, attempting fallback line-by-line parsing..."
    )
    return _fallback_line_parsing(translated_blob)


def _fallback_line_parsing_no_logger(translated_blob):
    """Enhanced fallback parsing for non-JSON formatted responses without logger dependency."""
    translations = {}
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

        # For unmatched lines, we just skip them silently in this version

    return translations


def _fallback_line_parsing(translated_blob):
    """Enhanced fallback parsing for non-JSON formatted responses."""
    translations = {}
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
            logger.warning(f"Could not parse line: {l[:100]}...")

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


# ===== TRUNCATION REPAIR FUNCTIONS =====


def detect_truncation_issues(content):
    """Detect if content has truncation issues."""
    if not content:
        return False

    # Check for markdown code blocks that are incomplete
    if content.startswith('```json') and not content.rstrip().endswith('```'):
        return True

    # Check for incomplete JSON structures
    if content.count('{') > content.count('}'):
        return True

    # Check for incomplete lines at the end
    lines = content.strip().split('\n')
    if lines and lines[-1].strip() and not lines[-1].strip().endswith(
        ('}', '"', ',')):
        return True

    return False


def fix_truncated_content(content, batch_id="unknown"):
    """Fix truncated markdown/JSON content."""
    global logger

    if not content.startswith('```json'):
        return content

    # Check if it's truncated (missing closing backticks)
    if not content.rstrip().endswith('```'):
        if logger:
            logger.info(f"Batch {batch_id}: Fixing truncated content...")

        # Extract JSON part
        json_match = re.search(r'```json\s*\n(\{.*)', content, re.DOTALL)
        if json_match:
            json_part = json_match.group(1)

            # Fix incomplete JSON
            fixed_json = fix_incomplete_json(json_part, batch_id)
            if fixed_json:
                return f"```json\n{fixed_json}\n```"

    return content


def fix_incomplete_json(json_str, batch_id="unknown"):
    """Fix incomplete JSON by adding missing closing brackets."""
    global logger

    # Clean up the string
    json_str = json_str.rstrip().rstrip(',')

    # Count braces
    open_braces = json_str.count('{')
    close_braces = json_str.count('}')

    if open_braces > close_braces:
        # Add missing closing braces
        missing_braces = open_braces - close_braces
        json_str += '\n' + '}' * missing_braces

        try:
            # Validate the fixed JSON
            parsed = json.loads(json_str)
            if logger:
                logger.info(
                    f"Batch {batch_id}: Successfully fixed JSON with {missing_braces} missing braces"
                )
            return json.dumps(parsed, ensure_ascii=False, indent=4)
        except json.JSONDecodeError:
            if logger:
                logger.warning(
                    f"Batch {batch_id}: Simple brace fix failed, trying alternative approach"
                )

    # Alternative: find last complete entry and close properly
    lines = json_str.split('\n')
    last_valid_line = None

    for i in range(len(lines) - 1, -1, -1):
        line = lines[i].strip()
        # Look for complete translation entry pattern
        if re.match(r'\s*"[^"]*":\s*"[^"]*"', line):
            last_valid_line = i
            break

    if last_valid_line is not None:
        # Keep only complete entries
        valid_lines = lines[:last_valid_line + 1]
        if valid_lines:
            valid_lines[-1] = valid_lines[-1].rstrip().rstrip(',')

        reconstructed = '\n'.join(valid_lines)

        # Add missing braces
        open_braces = reconstructed.count('{')
        close_braces = reconstructed.count('}')
        missing_braces = open_braces - close_braces

        if missing_braces > 0:
            reconstructed += '\n' + '}' * missing_braces

        try:
            parsed = json.loads(reconstructed)
            if logger:
                logger.info(
                    f"Batch {batch_id}: Successfully reconstructed JSON from {len(valid_lines)} valid lines"
                )
            return json.dumps(parsed, ensure_ascii=False, indent=4)
        except json.JSONDecodeError:
            if logger:
                logger.warning(f"Batch {batch_id}: JSON reconstruction failed")

    return None


def extract_json_from_markdown(content, batch_id="unknown"):
    """Extract JSON content from markdown code blocks."""
    global logger

    # Pattern to match ```json ... ```
    json_match = re.search(r'```json\s*\n(\{.*?\})\s*\n```', content,
                           re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
        try:
            # Validate the JSON
            parsed = json.loads(json_str)
            # Return clean, formatted JSON
            return json.dumps(parsed,
                              ensure_ascii=False,
                              separators=(',', ': '))
        except json.JSONDecodeError as e:
            if logger:
                logger.warning(
                    f"Batch {batch_id}: Invalid JSON in markdown - {e}")
    else:
        if logger:
            logger.warning(
                f"Batch {batch_id}: No JSON found in markdown block")

    return None


def attempt_auto_repair(content, batch_id):
    """Attempt to automatically repair truncated content."""
    global logger

    if not AUTO_REPAIR_ENABLED:
        return None

    if logger:
        logger.info(f"Attempting auto-repair for batch {batch_id}")

    # Step 1: Fix truncated content if needed
    fixed_content = fix_truncated_content(content, batch_id)
    if fixed_content != content:
        if logger:
            logger.info(f"Batch {batch_id}: Content truncation fixed")

    # Step 2: Extract JSON from markdown
    clean_json = extract_json_from_markdown(fixed_content, batch_id)

    if clean_json:
        try:
            # Validate and count translations
            translations = json.loads(clean_json)
            translation_count = len(translations)

            if logger:
                logger.info(
                    f"Batch {batch_id}: Auto-repair successful - extracted {translation_count} translations"
                )

            return translations
        except json.JSONDecodeError:
            if logger:
                logger.error(
                    f"Batch {batch_id}: Auto-repair failed - invalid JSON output"
                )
    else:
        if logger:
            logger.error(
                f"Batch {batch_id}: Auto-repair failed - could not extract JSON"
            )

    return None


def repair_failed_batch(batch_content, batch_id):
    """Comprehensive repair attempt for a failed batch."""
    global logger

    if not batch_content:
        return {}

    if logger:
        logger.info(f"Starting comprehensive repair for batch {batch_id}")

    # Try auto-repair first
    repair_result = attempt_auto_repair(batch_content, batch_id)
    if repair_result:
        return repair_result

    # Fallback: try the existing parsing methods
    if logger:
        logger.info(
            f"Auto-repair failed for {batch_id}, trying fallback parsing")

    # Use existing split_translations_by_id function as fallback
    fallback_translations = split_translations_by_id(batch_content)

    if fallback_translations:
        if logger:
            logger.info(
                f"Batch {batch_id}: Fallback parsing successful - extracted {len(fallback_translations)} translations"
            )
        return fallback_translations

    if logger:
        logger.error(f"Batch {batch_id}: All repair attempts failed")
    return {}


def process_results(input_csv, output_jsonl, final_csv, batches):
    """Process batch results and create final CSV."""
    logger.info(f"Processing results...")

    # Setup missing translations log file
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    csv_stem = Path(final_csv).stem
    missing_log_file = f"missing_translations_{csv_stem}_{timestamp}.log"

    logger.info(f"Missing translations will be logged to: {missing_log_file}")

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
    logger.info(f"Found {len(model_outputs)} batch responses")

    # Create batch mapping
    batch_mapping = {}
    for i, batch_data in enumerate(batches, 1):
        custom_id = f"batch-{i:04d}"
        description_ids = [desc_id for desc_id, _ in batch_data]
        batch_mapping[custom_id] = description_ids

    # Write final CSV and missing translations log
    with open(final_csv, "w", newline="", encoding="utf-8-sig") as csvf, \
         open(missing_log_file, 'w', encoding='utf-8') as missing_log:

        writer = csv.writer(csvf)
        writer.writerow(
            ["description_id", "english_sentence", "translated_sentence"])

        # Write missing translations log header
        missing_log.write(f"Missing Translations Log\n")
        missing_log.write(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        missing_log.write(f"Input CSV: {input_csv}\n")
        missing_log.write(f"Output CSV: {final_csv}\n")
        missing_log.write(f"JSONL Source: {output_jsonl}\n")
        missing_log.write(f"Total Batches: {len(batch_mapping)}\n")
        missing_log.write("-" * 70 + "\n\n")

        all_failed = []
        all_extra = []
        all_success = 0
        all_shifted = []
        all_suspicious = []
        missing_ids = []

        for custom_id, description_ids in batch_mapping.items():
            logger.info(f"Processing {custom_id}...")
            translated_blob = model_outputs.get(custom_id)
            translations = split_translations_by_id(translated_blob)
            logger.info(f"  Extracted {len(translations)} translations")
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
                    missing_ids.append(description_id)
                    batch_rows.append((description_id, english_sentence,
                                       "[TRANSLATION_FAILED]"))

                    # Log to missing translations file
                    missing_log.write(
                        f"No translation found for ID {description_id}\n")
                    missing_log.write(f"  Batch: {custom_id}\n")
                    missing_log.write(f"  English: {english_sentence}\n")
                    missing_log.write(f"  Status: TRANSLATION_FAILED\n\n")
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
                logger.error(
                    f"[ERROR] Batch {custom_id}: Missing translations for:")
                for did, eng in missing:
                    logger.error(f"  - {did}: {eng}")
                all_failed.extend([(custom_id, did, eng)
                                   for did, eng in missing])

            if extra:
                logger.warning(
                    f"[WARNING] Batch {custom_id}: Extra translations returned:"
                )
                for tid, tval in extra:
                    logger.warning(f"  - {tid}: {tval}")
                all_extra.extend([(custom_id, tid, tval)
                                  for tid, tval in extra])

        # Write summary to missing translations log
        missing_log.write("-" * 70 + "\n")
        missing_log.write("SUMMARY\n")
        missing_log.write("-" * 70 + "\n")
        missing_log.write(f"Total batches processed: {len(batch_mapping)}\n")
        missing_log.write(f"Total rows processed: {len(original_data)}\n")
        missing_log.write(f"Successful translations: {all_success}\n")
        missing_log.write(f"Failed translations: {len(all_failed)}\n")
        missing_log.write(
            f"Success rate: {(all_success/len(original_data)*100):.1f}%\n"
            if len(original_data) > 0 else "Success rate: N/A\n")
        missing_log.write(
            f"Missing IDs: {', '.join(missing_ids) if missing_ids else 'None'}\n"
        )
        missing_log.write(f"Extra translations: {len(all_extra)}\n")
        missing_log.write(f"Suspicious translations: {len(all_suspicious)}\n")
        missing_log.write(f"Shifted translations: {len(all_shifted)}\n")

    # Print summary
    total_processed = len(original_data)
    logger.info(f"\n=== TRANSLATION RESULTS ===")
    logger.info(f"Successful translations: {all_success}")
    logger.info(f"Failed translations: {len(all_failed)}")
    logger.info(f"Total processed: {total_processed}")
    if total_processed > 0:
        logger.info(f"Success rate: {all_success/total_processed*100:.1f}%")
    logger.info(f"Final output: {final_csv}")
    logger.info(f"Missing translations log: {missing_log_file}")

    logger.info(
        f"\n[SUMMARY] {all_success} successful translations written to {final_csv}"
    )

    if all_failed:
        logger.warning(f"[SUMMARY] {len(all_failed)} missing translations:")
        for custom_id, did, eng in all_failed:
            logger.warning(f"  - Batch {custom_id}, {did}: {eng}")

    if all_extra:
        logger.warning(
            f"[SUMMARY] {len(all_extra)} extra translations returned:")
        for custom_id, tid, tval in all_extra:
            logger.warning(f"  - Batch {custom_id}, {tid}: {tval}")

    if all_suspicious:
        logger.warning(
            f"[SUSPICIOUS] {len(all_suspicious)} suspicious translations detected:"
        )
        for custom_id, did, eng, trans in all_suspicious:
            logger.warning(
                f"  - Batch {custom_id}, {did}: '{trans}' (English: '{eng[:40]}...')"
            )

    if all_shifted:
        logger.warning(
            f"[SHIFT WARNING] {len(all_shifted)} possible shifted translations detected:"
        )
        for custom_id, missing_id, missing_eng, shifted_from_id, shifted_trans in all_shifted:
            logger.warning(
                f"  - Batch {custom_id}: Likely translation for {missing_id} ('{missing_eng[:40]}...') was output for {shifted_from_id}: '{shifted_trans[:40]}...'"
            )

    # Final status message
    if not all_failed and not all_extra and not all_shifted and not all_suspicious:
        logger.info(
            f"\n🎉 SUCCESS: All {all_success} translations completed perfectly!"
        )
        logger.info("[SUMMARY] All translations matched by description_id.")
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

        if len(all_failed) > 0:
            print(f"\n📋 Missing translations logged to: {missing_log_file}")
            print(
                f"   Check this file for detailed list of {len(all_failed)} missing IDs"
            )


def analyze_jsonl_errors(jsonl_file_path,
                         input_csv_path=None,
                         error_log_path=None):
    """
    Comprehensive error analysis of JSONL output files with auto-repair capability.
    Analyzes JSON parsing errors, missing translations, failed responses, and suspicious translations.
    Automatically attempts to repair truncated responses when detected.
    
    Args:
        jsonl_file_path: Path to the JSONL output file to analyze
        input_csv_path: Optional path to original input CSV for comparison
        error_log_path: Optional path for error log file (auto-generated if not provided)
    
    Returns:
        Dictionary containing error analysis results
    """

    # Setup error log file
    if error_log_path is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        jsonl_stem = Path(jsonl_file_path).stem
        error_log_path = f"error_analysis_{jsonl_stem}_{timestamp}.log"

    # Create error log directory if needed
    error_log_dir = Path(error_log_path).parent
    if error_log_dir != Path('.'):
        error_log_dir.mkdir(exist_ok=True)

    # Initialize analysis results
    analysis_results = {
        'total_batches': 0,
        'successful_batches': 0,
        'failed_batches': 0,
        'repaired_batches': 0,  # New: track auto-repairs
        'json_parse_errors': [],
        'missing_translations': [],
        'suspicious_translations': [],
        'empty_responses': [],
        'partial_failures': [],
        'status_code_errors': [],
        'response_format_errors': [],
        'repair_attempts': [],  # New: track repair attempts
        'repair_successes': [],  # New: track successful repairs
        'summary': {}
    }

    # Load original input data if provided
    original_data = {}
    if input_csv_path and Path(input_csv_path).exists():
        try:
            with open(input_csv_path, 'r', encoding='utf-8') as f:
                reader = csv.reader(f)
                next(reader, None)  # Skip header
                for row in reader:
                    if len(row) >= 2:
                        original_data[row[0].strip()] = row[1].strip()
        except Exception as e:
            print(f"Warning: Could not load input CSV: {e}")

    # Create backup of original JSONL if repairs are enabled
    repaired_jsonl_path = None
    if AUTO_REPAIR_ENABLED and BACKUP_FAILED_BATCHES:
        repaired_jsonl_path = jsonl_file_path.replace('.jsonl',
                                                      '_repaired.jsonl')

    # Start error analysis log
    with open(error_log_path, 'w', encoding='utf-8') as error_log:

        def log_error(message):
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            error_log.write(f"[{timestamp}] {message}\n")
            print(f"ERROR ANALYSIS: {message}")

        log_error("=== JSONL ERROR ANALYSIS WITH AUTO-REPAIR STARTED ===")
        log_error(f"Analyzing file: {jsonl_file_path}")
        if input_csv_path:
            log_error(f"Comparing against input: {input_csv_path}")
        log_error(f"Auto-repair enabled: {AUTO_REPAIR_ENABLED}")
        log_error(f"Error log: {error_log_path}")
        log_error("")

        # Check if JSONL file exists
        if not Path(jsonl_file_path).exists():
            log_error(f"CRITICAL: JSONL file not found: {jsonl_file_path}")
            analysis_results['summary'][
                'critical_error'] = f"File not found: {jsonl_file_path}"
            return analysis_results

        # Prepare repaired JSONL file if needed
        repaired_entries = []

        # Analyze each line in JSONL
        try:
            with open(jsonl_file_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue

                    analysis_results['total_batches'] += 1
                    custom_id = f"Unknown_Batch_{line_num}"
                    current_entry = None

                    try:
                        # Parse the JSONL line
                        item = json.loads(line)
                        custom_id = item.get('custom_id', custom_id)
                        current_entry = item.copy()  # Keep original for repair

                        # Check for HTTP status code errors
                        if 'response' in item:
                            status_code = item['response'].get('status_code')
                            if status_code != 200:
                                error_info = {
                                    'batch_id':
                                    custom_id,
                                    'status_code':
                                    status_code,
                                    'line_number':
                                    line_num,
                                    'error_details':
                                    item.get('error', 'Unknown error')
                                }
                                analysis_results['status_code_errors'].append(
                                    error_info)
                                log_error(
                                    f"HTTP Error in {custom_id}: Status {status_code}"
                                )
                                continue

                        # Extract content from response
                        try:
                            content = item["response"]["body"]["choices"][0][
                                "message"]["content"]
                        except KeyError as e:
                            error_info = {
                                'batch_id': custom_id,
                                'line_number': line_num,
                                'missing_key': str(e),
                                'available_keys': list(item.keys())
                            }
                            analysis_results['response_format_errors'].append(
                                error_info)
                            log_error(
                                f"Response format error in {custom_id}: Missing key {e}"
                            )
                            continue

                        # Check for empty responses
                        if not content or not content.strip():
                            error_info = {
                                'batch_id': custom_id,
                                'line_number': line_num,
                                'content': content
                            }
                            analysis_results['empty_responses'].append(
                                error_info)
                            log_error(f"Empty response in {custom_id}")
                            continue

                        # Try to parse translations from content using local parsing
                        translations = {}

                        # Try JSON parsing first (modified from split_translations_by_id without logger)
                        for strategy_num, cleanup_func in enumerate([
                                _cleanup_markdown_basic,
                                _cleanup_markdown_aggressive,
                                _cleanup_markdown_multiline,
                                _cleanup_unicode_and_escapes
                        ], 1):
                            try:
                                cleaned_blob = cleanup_func(content)
                                if not cleaned_blob:
                                    continue

                                # Try to parse as JSON
                                json_data = json.loads(cleaned_blob)
                                if isinstance(json_data, dict) and json_data:
                                    # Direct JSON mapping - this is what we want
                                    for desc_id, translation in json_data.items(
                                    ):
                                        if translation and str(
                                                translation).strip():
                                            clean_translation = str(
                                                translation).strip()
                                            if not is_suspicious_translation(
                                                    clean_translation):
                                                translations[
                                                    str(desc_id
                                                        )] = clean_translation
                                    break
                            except json.JSONDecodeError:
                                continue
                            except Exception:
                                continue

                        # If JSON parsing failed, try fallback
                        if not translations:
                            translations = _fallback_line_parsing_no_logger(
                                content)

                        # === AUTO-REPAIR LOGIC ===
                        if not translations and AUTO_REPAIR_ENABLED:
                            # Detect if this might be a truncation issue
                            if detect_truncation_issues(content):
                                log_error(
                                    f"Truncation detected in {custom_id}, attempting auto-repair..."
                                )

                                repair_info = {
                                    'batch_id': custom_id,
                                    'line_number': line_num,
                                    'repair_trigger': 'truncation_detected',
                                    'original_content_length': len(content)
                                }
                                analysis_results['repair_attempts'].append(
                                    repair_info)

                                # Attempt repair
                                repaired_translations = repair_failed_batch(
                                    content, custom_id)

                                if repaired_translations:
                                    translations = repaired_translations
                                    analysis_results['repaired_batches'] += 1

                                    # Update repair info with success
                                    repair_success = {
                                        'batch_id':
                                        custom_id,
                                        'line_number':
                                        line_num,
                                        'translations_recovered':
                                        len(repaired_translations),
                                        'repair_method':
                                        'auto_truncation_fix'
                                    }
                                    analysis_results[
                                        'repair_successes'].append(
                                            repair_success)

                                    # If we have a repaired entry, update the content for backup
                                    if current_entry and repaired_jsonl_path:
                                        # Create clean JSON content for the repaired entry
                                        clean_json = json.dumps(
                                            repaired_translations,
                                            ensure_ascii=False,
                                            separators=(',', ': '))
                                        current_entry["response"]["body"][
                                            "choices"][0]["message"][
                                                "content"] = clean_json
                                        repaired_entries.append(current_entry)

                                    log_error(
                                        f"AUTO-REPAIR SUCCESS: {custom_id} - recovered {len(repaired_translations)} translations"
                                    )
                                else:
                                    log_error(
                                        f"AUTO-REPAIR FAILED: {custom_id} - could not recover translations"
                                    )

                        if not translations:
                            # JSON parsing failed completely
                            error_info = {
                                'batch_id':
                                custom_id,
                                'line_number':
                                line_num,
                                'content_preview':
                                content[:200] +
                                "..." if len(content) > 200 else content,
                                'content_length':
                                len(content),
                                'parse_error':
                                'Failed to extract any translations',
                                'truncation_detected':
                                detect_truncation_issues(content)
                            }
                            analysis_results['json_parse_errors'].append(
                                error_info)
                            log_error(
                                f"JSON parse failure in {custom_id}: No translations extracted"
                            )
                            analysis_results['failed_batches'] += 1
                        else:
                            # Partial success - analyze what was extracted
                            analysis_results['successful_batches'] += 1

                            # Check for suspicious translations
                            suspicious_count = 0
                            for desc_id, translation in translations.items():
                                if is_suspicious_translation(translation):
                                    suspicious_count += 1
                                    error_info = {
                                        'batch_id':
                                        custom_id,
                                        'description_id':
                                        desc_id,
                                        'translation':
                                        translation,
                                        'original_text':
                                        original_data.get(desc_id, 'Unknown'),
                                        'reason':
                                        'Suspicious translation pattern'
                                    }
                                    analysis_results[
                                        'suspicious_translations'].append(
                                            error_info)

                            if suspicious_count > 0:
                                log_error(
                                    f"Found {suspicious_count} suspicious translations in {custom_id}"
                                )

                            log_error(
                                f"Batch {custom_id}: Extracted {len(translations)} translations, {suspicious_count} suspicious"
                            )

                            # Add successful entry to repaired file (even if not repaired)
                            if repaired_jsonl_path:
                                repaired_entries.append(current_entry)

                    except json.JSONDecodeError as e:
                        error_info = {
                            'batch_id':
                            custom_id,
                            'line_number':
                            line_num,
                            'json_error':
                            str(e),
                            'content_preview':
                            line[:200] + "..." if len(line) > 200 else line
                        }
                        analysis_results['json_parse_errors'].append(
                            error_info)
                        log_error(f"JSON decode error at line {line_num}: {e}")
                        analysis_results['failed_batches'] += 1

                    except Exception as e:
                        error_info = {
                            'batch_id': custom_id,
                            'line_number': line_num,
                            'unexpected_error': str(e),
                            'error_type': type(e).__name__
                        }
                        analysis_results['response_format_errors'].append(
                            error_info)
                        log_error(f"Unexpected error at line {line_num}: {e}")
                        analysis_results['failed_batches'] += 1

        except Exception as e:
            log_error(f"CRITICAL: Could not read JSONL file: {e}")
            analysis_results['summary']['critical_error'] = str(e)
            return analysis_results

        # Write repaired JSONL file if we have repairs
        if repaired_entries and repaired_jsonl_path:
            try:
                with open(repaired_jsonl_path, 'w',
                          encoding='utf-8') as repaired_file:
                    for entry in repaired_entries:
                        repaired_file.write(
                            json.dumps(entry, ensure_ascii=False) + '\n')
                log_error(f"Repaired JSONL written to: {repaired_jsonl_path}")
            except Exception as e:
                log_error(f"Failed to write repaired JSONL: {e}")

        # Generate summary
        total = analysis_results['total_batches']
        successful = analysis_results['successful_batches']
        failed = analysis_results['failed_batches']
        repaired = analysis_results['repaired_batches']

        success_rate = (successful / total * 100) if total > 0 else 0
        repair_rate = (repaired / failed * 100) if failed > 0 else 0

        analysis_results['summary'] = {
            'total_batches':
            total,
            'successful_batches':
            successful,
            'failed_batches':
            failed,
            'repaired_batches':
            repaired,
            'success_rate_percentage':
            round(success_rate, 2),
            'repair_rate_percentage':
            round(repair_rate, 2),
            'effective_success_rate_percentage':
            round(((successful + repaired) / total * 100) if total > 0 else 0,
                  2),
            'json_parse_errors_count':
            len(analysis_results['json_parse_errors']),
            'suspicious_translations_count':
            len(analysis_results['suspicious_translations']),
            'response_format_errors_count':
            len(analysis_results['response_format_errors']),
            'empty_responses_count':
            len(analysis_results['empty_responses']),
            'status_code_errors_count':
            len(analysis_results['status_code_errors']),
            'repair_attempts_count':
            len(analysis_results['repair_attempts']),
            'repair_successes_count':
            len(analysis_results['repair_successes'])
        }

        log_error("")
        log_error("=== ANALYSIS SUMMARY ===")
        log_error(f"Total batches analyzed: {total}")
        log_error(f"Successful batches: {successful}")
        log_error(f"Failed batches: {failed}")
        log_error(f"Auto-repaired batches: {repaired}")
        log_error(f"Original success rate: {success_rate:.2f}%")
        log_error(f"Repair success rate: {repair_rate:.2f}%")
        log_error(
            f"Effective success rate: {((successful + repaired) / total * 100) if total > 0 else 0:.2f}%"
        )
        log_error(
            f"JSON parse errors: {len(analysis_results['json_parse_errors'])}")
        log_error(
            f"Suspicious translations: {len(analysis_results['suspicious_translations'])}"
        )
        log_error(
            f"Empty responses: {len(analysis_results['empty_responses'])}")
        log_error(
            f"HTTP status errors: {len(analysis_results['status_code_errors'])}"
        )
        log_error(
            f"Response format errors: {len(analysis_results['response_format_errors'])}"
        )
        log_error(
            f"Repair attempts: {len(analysis_results['repair_attempts'])}")
        log_error(
            f"Successful repairs: {len(analysis_results['repair_successes'])}")
        log_error("")

        # Detailed error breakdown
        if analysis_results['json_parse_errors']:
            log_error("=== JSON PARSE ERRORS DETAILS ===")
            for error in analysis_results[
                    'json_parse_errors'][:10]:  # Show first 10
                log_error(
                    f"Batch: {error['batch_id']}, Line: {error['line_number']}"
                )
                log_error(
                    f"  Error: {error.get('json_error', error.get('parse_error', 'Unknown'))}"
                )
                log_error(
                    f"  Truncation detected: {error.get('truncation_detected', 'Unknown')}"
                )
                log_error(
                    f"  Preview: {error.get('content_preview', 'N/A')[:100]}..."
                )
                log_error("")

        if analysis_results['repair_successes']:
            log_error("=== SUCCESSFUL REPAIRS DETAILS ===")
            for repair in analysis_results[
                    'repair_successes'][:10]:  # Show first 10
                log_error(
                    f"Batch: {repair['batch_id']}, Line: {repair['line_number']}"
                )
                log_error(f"  Method: {repair['repair_method']}")
                log_error(
                    f"  Translations recovered: {repair['translations_recovered']}"
                )
                log_error("")

        if analysis_results['suspicious_translations']:
            log_error("=== SUSPICIOUS TRANSLATIONS DETAILS ===")
            for error in analysis_results[
                    'suspicious_translations'][:10]:  # Show first 10
                log_error(
                    f"Batch: {error['batch_id']}, ID: {error['description_id']}"
                )
                log_error(f"  Original: {error['original_text'][:100]}...")
                log_error(f"  Translation: {error['translation']}")
                log_error(f"  Reason: {error['reason']}")
                log_error("")

        log_error("=== ERROR ANALYSIS WITH AUTO-REPAIR COMPLETED ===")
        log_error(f"Detailed results saved to: {error_log_path}")
        if repaired_jsonl_path and repaired_entries:
            log_error(f"Repaired JSONL saved to: {repaired_jsonl_path}")

    print(f"\nError analysis with auto-repair completed!")
    print(f"Total batches: {total}")
    print(f"Original success rate: {success_rate:.2f}%")
    if repaired > 0:
        print(f"Auto-repaired batches: {repaired}")
        print(
            f"Effective success rate: {((successful + repaired) / total * 100) if total > 0 else 0:.2f}%"
        )
    print(f"Detailed error log saved to: {error_log_path}")
    if repaired_jsonl_path and repaired_entries:
        print(f"Repaired JSONL saved to: {repaired_jsonl_path}")

    return analysis_results


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print(
            "  Translation: python auto_translate.py <input_csv> <target_language> <output_csv>"
        )
        print(
            "  Error Analysis: python auto_translate.py analyze <jsonl_file> [input_csv]"
        )
        print()
        print("Examples:")
        print(
            "  python auto_translate.py test_input.csv Hindi translations.csv")
        print("  python auto_translate.py analyze output.jsonl")
        print("  python auto_translate.py analyze output.jsonl input.csv")
        sys.exit(1)

    # Check if this is an error analysis request
    if sys.argv[1] == "analyze":
        if len(sys.argv) < 3:
            print("Error: analyze command requires JSONL file path")
            print(
                "Usage: python auto_translate.py analyze <jsonl_file> [input_csv]"
            )
            sys.exit(1)

        jsonl_file = sys.argv[2]
        input_csv = sys.argv[3] if len(sys.argv) > 3 else None

        # Perform error analysis
        results = analyze_jsonl_errors(jsonl_file, input_csv)

        # Print summary
        print("\n" + "=" * 70)
        print("ERROR ANALYSIS WITH AUTO-REPAIR SUMMARY")
        print("=" * 70)
        summary = results['summary']

        # Basic metrics
        print(f"Total Batches: {summary.get('total_batches', 0)}")
        print(f"Successful Batches: {summary.get('successful_batches', 0)}")
        print(f"Failed Batches: {summary.get('failed_batches', 0)}")
        print(f"Auto-Repaired Batches: {summary.get('repaired_batches', 0)}")
        print("-" * 70)

        # Success rates
        print(
            f"Original Success Rate: {summary.get('success_rate_percentage', 0):.2f}%"
        )
        if summary.get('repaired_batches', 0) > 0:
            print(
                f"Repair Success Rate: {summary.get('repair_rate_percentage', 0):.2f}%"
            )
            print(
                f"Effective Success Rate: {summary.get('effective_success_rate_percentage', 0):.2f}%"
            )
        print("-" * 70)

        # Error breakdown
        print("Error Breakdown:")
        print(
            f"  JSON Parse Errors: {summary.get('json_parse_errors_count', 0)}"
        )
        print(
            f"  Suspicious Translations: {summary.get('suspicious_translations_count', 0)}"
        )
        print(f"  Empty Responses: {summary.get('empty_responses_count', 0)}")
        print(
            f"  HTTP Status Errors: {summary.get('status_code_errors_count', 0)}"
        )
        print(
            f"  Response Format Errors: {summary.get('response_format_errors_count', 0)}"
        )
        print("-" * 70)

        # Repair metrics
        if AUTO_REPAIR_ENABLED:
            print("Auto-Repair Metrics:")
            print(
                f"  Repair Attempts: {summary.get('repair_attempts_count', 0)}"
            )
            print(
                f"  Successful Repairs: {summary.get('repair_successes_count', 0)}"
            )
            repair_effectiveness = 0
            if summary.get('repair_attempts_count', 0) > 0:
                repair_effectiveness = (
                    summary.get('repair_successes_count', 0) /
                    summary.get('repair_attempts_count', 0)) * 100
            print(f"  Repair Effectiveness: {repair_effectiveness:.1f}%")
        else:
            print("Auto-Repair: DISABLED")

        print("=" * 70)
        return

    # Regular translation mode - validate arguments
    if len(sys.argv) != 4:
        print("Error: Translation mode requires exactly 3 arguments")
        print(
            "Usage: python auto_translate.py <input_csv> <target_language> <output_csv>"
        )
        print(
            "Example: python auto_translate.py test_input.csv Hindi translations.csv"
        )
        sys.exit(1)

    # Extract arguments for translation
    input_csv = sys.argv[1]
    target_language = sys.argv[2]
    output_csv = sys.argv[3]

    # Add error handling for the translation pipeline
    try:
        run_translation_pipeline(input_csv, target_language, output_csv)
    except Exception as e:
        print(f"Error during translation: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def run_translation_pipeline(input_csv, target_language, output_csv):
    """Execute the full translation pipeline."""
    global logger

    # Create unique file names based on input file
    input_stem = Path(input_csv).stem
    timestamp = int(time.time())
    unique_id = f"{input_stem}_{timestamp}"

    # Initialize logging
    log_filename = f"translation_log_{unique_id}.txt"
    log_path = setup_logging(log_filename)
    logger = DualLogger(log_path)

    logger.info("=== TRANSLATION PIPELINE STARTED ===")
    logger.info(f"Input CSV: {input_csv}")
    logger.info(f"Target Language: {target_language}")
    logger.info(f"Output CSV: {output_csv}")
    logger.info(f"Unique ID: {unique_id}")
    logger.info(f"Log file: {log_path}")

    # Initialize batch tracking
    initialize_batch_tracking()

    # Unique file names
    jsonl_file = f"{unique_id}_batch.jsonl"
    output_jsonl = f"{unique_id}_output.jsonl"
    error_jsonl = f"{unique_id}_errors.jsonl"

    # Step 1: Create JSONL from CSV
    logger.info("=== Step 1: Creating JSONL from CSV ===")
    batches = create_jsonl_from_csv(input_csv, jsonl_file, target_language)

    # Step 2: Upload and create batch job
    logger.info("\n=== Step 2: Uploading and creating batch job ===")
    input_file_id = upload_batch_file(jsonl_file)
    job = create_batch_job(input_file_id)
    job_id = job.id

    # Add initial batch record to tracking
    add_batch_record(batch_id=unique_id,
                     input_file=input_csv,
                     job_id=job_id,
                     status=job.status,
                     timestamp=timestamp,
                     target_language=target_language,
                     output_file=output_csv)

    logger.info(f"\n{'='*50}")
    logger.info(f"BATCH JOB SUBMITTED SUCCESSFULLY!")
    logger.info(f"Job ID: {job_id}")
    logger.info(f"Status: {job.status}")
    logger.info(f"Unique ID: {unique_id}")
    logger.info(f"{'='*50}")

    # Step 3: Wait for completion
    logger.info("\n=== Step 3: Waiting for job completion ===")
    job = poll_until_done(job_id)

    # Update batch status
    update_batch_status(job_id, job.status)

    if job.status == "completed":
        logger.info("\n=== Step 4: Processing results ===")

        # Download results
        if download_file(job.output_file_id, output_jsonl):
            # Download errors if they exist
            if hasattr(job, 'error_file_id') and job.error_file_id:
                download_file(job.error_file_id, error_jsonl)
                logger.warning(f"Some errors occurred. Check {error_jsonl}")

            # Process results
            process_results(input_csv, output_jsonl, output_csv, batches)

            # Update batch record with final output file
            update_batch_status(job_id, "completed", output_csv)

            logger.info(
                f"\n[+] Pipeline complete! Final translations in: {output_csv}"
            )
            logger.info("=== TRANSLATION PIPELINE COMPLETED SUCCESSFULLY ===")
        else:
            logger.error("Failed to download results")
            update_batch_status(job_id, "download_failed")
    elif job.status == "failed":
        logger.error("Job failed!")
        update_batch_status(job_id, "failed")
        if hasattr(job, 'error_file_id') and job.error_file_id:
            download_file(job.error_file_id, error_jsonl)
            logger.error(f"Check {error_jsonl} for details")
        logger.error("=== TRANSLATION PIPELINE FAILED ===")
    else:
        logger.error(f"Unexpected job status: {job.status}")
        update_batch_status(job_id, f"unknown_{job.status}")
        logger.error("=== TRANSLATION PIPELINE ENDED WITH UNKNOWN STATUS ===")


if __name__ == "__main__":
    main()
