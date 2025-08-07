#!/usr/bin/env python3
"""
Simple script to process batch translation responses and merge with CSV
Usage: python process_translations.py
"""

import json
import re
import pandas as pd


def parse_batch_responses(jsonl_file_path):
    """Parse all batch responses from JSONL file"""
    translations = {}

    # Regex patterns
    format1_pattern = r"(\d+)\.\s*\('(\d+)',\s*'([^']+)'\)"
    format2_pattern = r"desc_(\d+)\.\s*([^\n]+)"

    with open(jsonl_file_path, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue

            try:
                # Parse JSON
                batch_data = json.loads(line)
                content = batch_data['response']['body']['choices'][0][
                    'message']['content']

                # Clean content (remove markdown)
                content = re.sub(r'```(?:plaintext)?\n?', '', content)
                content = re.sub(r'\n?```', '', content)

                # Try format 1: ('21', 'Telugu text')
                matches = re.findall(format1_pattern, content, re.UNICODE)
                for match in matches:
                    id_num = match[1]  # The ID from the tuple
                    telugu_text = match[2]
                    translations[id_num] = telugu_text

                # Try format 2: desc_492. Telugu text
                matches = re.findall(format2_pattern, content, re.UNICODE)
                for match in matches:
                    id_num = match[0]  # The number after desc_
                    telugu_text = match[1].strip()
                    translations[id_num] = telugu_text

                print(f"Processed line {line_num}")

            except Exception as e:
                print(f"Error processing line {line_num}: {e}")

    print(f"Total translations extracted: {len(translations)}")
    return translations


def merge_translations_with_csv(csv_file_path,
                                translations,
                                output_file_path=None):
    """Merge translations with CSV file"""

    # Read CSV
    df = pd.read_csv(csv_file_path)

    # Convert description_id to string for matching
    df['description_id'] = df['description_id'].astype(str)

    # Add translated column
    df['translated'] = df['description_id'].map(translations)

    # Report results
    mapped = df['translated'].notna().sum()
    total = len(df)
    print(f"\nMapping Results:")
    print(f"Successfully mapped: {mapped}/{total}")

    # Show sample mappings
    print(f"\nSample mappings:")
    sample_mapped = df[df['translated'].notna()].head(3)
    for _, row in sample_mapped.iterrows():
        print(f"ID {row['description_id']}: {row['english_sentence'][:50]}...")
        print(f"   -> {row['translated']}")

    # Show unmapped IDs
    unmapped = df[df['translated'].isna()]['description_id'].tolist()
    if unmapped:
        print(
            f"\nUnmapped IDs: {unmapped[:10]}{'...' if len(unmapped) > 10 else ''}"
        )

    # Save result
    if output_file_path is None:
        output_file_path = csv_file_path.replace('.csv',
                                                 '_with_translations.csv')

    df.to_csv(output_file_path, index=False, encoding='utf-8')
    print(f"\nResults saved to: {output_file_path}")

    return df


# Main execution
if __name__ == "__main__":
    # File paths - UPDATE THESE TO YOUR ACTUAL FILE PATHS
    JSONL_FILE = "input_test_1754458419_output.jsonl"  # Your batch responses file
    CSV_FILE = "input_folder/input_test.csv"  # Your CSV with description_id,english_sentence
    OUTPUT_FILE = "output_test.csv" # Output file

    try:
        print("Step 1: Parsing batch responses...")
        translations = parse_batch_responses(JSONL_FILE)

        print("\nStep 2: Merging with CSV...")
        result_df = merge_translations_with_csv(CSV_FILE, translations,
                                                OUTPUT_FILE)

        print("\nProcess completed successfully!")

    except FileNotFoundError as e:
        print(f"File not found: {e}")
        print(
            "Please update the file paths in the script to match your actual files."
        )
    except Exception as e:
        print(f"Error: {e}")
