#!/usr/bin/env python3
"""
Process existing batch results without creating new batch jobs.
Use this when you already have the output.jsonl file and just need to parse it correctly.
"""

import sys
import json
import csv
import re
from pathlib import Path


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
        print(f"JSON decode error: {e}")
        return {}

    return translations


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
            except Exception as e:
                print(f"Error extracting content for {cid}: {e}")
                content = None
            results[cid] = content
    return results


def process_existing_batch(input_csv, output_jsonl, final_csv):
    """Process existing batch results and create final CSV."""
    print(f"Processing existing batch results from {output_jsonl}...")

    # Load original data
    with open(input_csv, encoding="utf-8") as f:
        reader = csv.reader(f)
        next(reader)  # Skip header
        original_data = {}
        for row in reader:
            if len(row) > 1 and row[1].strip():
                description_id = row[0].strip()
                sentence = row[1].strip()
                original_data[description_id] = sentence

    # Parse model outputs
    model_outputs = parse_output_jsonl(output_jsonl)
    print(f"Found {len(model_outputs)} batch responses")

    # Write final CSV
    with open(final_csv, "w", newline="", encoding="utf-8-sig") as csvf:
        writer = csv.writer(csvf)
        writer.writerow(
            ["description_id", "english_sentence", "translated_sentence"])

        all_success = 0
        all_failed = 0
        all_translations = {}

        # Process each batch
        for custom_id, translated_blob in model_outputs.items():
            print(f"Processing {custom_id}...")
            translations = split_translations_by_id(translated_blob)
            print(f"  Extracted {len(translations)} translations")

            # Collect all translations
            all_translations.update(translations)

        # Write all translations in order of original CSV
        for description_id, english_sentence in original_data.items():
            translated_sentence = all_translations.get(description_id)

            if translated_sentence:
                writer.writerow(
                    [description_id, english_sentence, translated_sentence])
                all_success += 1
            else:
                writer.writerow(
                    [description_id, english_sentence, "[TRANSLATION_FAILED]"])
                all_failed += 1

    print(f"\n=== RESULTS ===")
    print(f"Successful translations: {all_success}")
    print(f"Failed translations: {all_failed}")
    print(f"Total processed: {len(original_data)}")
    print(f"Success rate: {all_success/len(original_data)*100:.1f}%")
    print(f"Final output: {final_csv}")


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python process_existing_batch.py <input_csv> <output_jsonl> <final_csv>"
        )
        print(
            "Example: python process_existing_batch.py input_test3.csv input_test3_1754561427_output.jsonl input_test3_fixed.csv"
        )
        sys.exit(1)

    input_csv = sys.argv[1]
    output_jsonl = sys.argv[2]
    final_csv = sys.argv[3]

    # Check if files exist
    if not Path(input_csv).exists():
        print(f"Error: Input CSV file '{input_csv}' not found")
        sys.exit(1)

    if not Path(output_jsonl).exists():
        print(f"Error: Output JSONL file '{output_jsonl}' not found")
        sys.exit(1)

    process_existing_batch(input_csv, output_jsonl, final_csv)


if __name__ == "__main__":
    main()
