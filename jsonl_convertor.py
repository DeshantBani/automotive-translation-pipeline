import csv
import json
import tiktoken
import sys
import os

# Set the model and token limit
MODEL_NAME = "gpt-4o"
MODEL_TOKEN_LIMIT = 16000
EXPECTED_OUTPUT_FACTOR = 1.2  # Estimate: output may be up to 1.2x input tokens


def get_system_prompt(target_language):
    return f"""You are an expert automotive translator proficient in English and {target_language}. Your task is to translate technical automotive sentences from English into accurate, formal {target_language}. Ensure technical automotive terminology is translated precisely. If a specific automotive technical term, diagnostic code, or component name doesn't have an exact {target_language} equivalent, retain it in English or transliterate it clearly into {target_language} script.\n\n- Preserve numeric codes, such as fault codes (e.g., P0089), as-is.\n- The sentences provided by the user are identified by their unique description_id. Provide translations in {target_language} strictly following the exact description_id and sequence of the input sentences. Do not alter the sequence under any circumstance.\n- Only output translated sentences in {target_language} with the respective description_id. Do NOT include explanations or additional text.\n\nExample:\nInput:\ndesc_001. The fault code P0089 indicates that there is an issue with the performance of the fuel pressure regulator 1. This may cause a decrease in fuel efficiency, difficulty starting the engine, or poor engine performance.\ndesc_002. Engine misfire can occur due to issues with the ignition coils or spark plugs.\n\nExpected Output:\ndesc_001. <translation>\ndesc_002. <translation>"""


def count_tokens(text, encoding):
    return len(encoding.encode(text))


def create_jsonl_from_csv(csv_filename,
                          jsonl_filename,
                          target_language,
                          model_name=MODEL_NAME,
                          token_limit=MODEL_TOKEN_LIMIT,
                          custom_id_prefix=None):
    """
    Create JSONL file from CSV with description_id support and dynamic batching based on token count.
    CSV format: description_id, text
    """
    encoding = tiktoken.encoding_for_model(model_name)
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
    batch_start_idx = 0

    for idx, (description_id, sentence) in enumerate(data_rows):
        # Prepare the line as it will appear in the user prompt
        line = f"{description_id}. {sentence}"
        line_tokens = count_tokens(line + "\n", encoding)
        # Estimate output tokens for this line
        est_output_tokens = int(line_tokens * EXPECTED_OUTPUT_FACTOR)
        # Total tokens if we add this line
        total_if_added = current_tokens + line_tokens + est_output_tokens
        if total_if_added > token_limit and current_batch:
            # Write current batch and start a new one
            batches.append(current_batch)
            current_batch = []
            current_tokens = system_prompt_tokens
            batch_start_idx = idx
        current_batch.append((description_id, sentence))
        current_tokens += line_tokens + est_output_tokens
    if current_batch:
        batches.append(current_batch)

    with open(jsonl_filename, 'w', encoding='utf-8') as jsonl_file:
        for batch_num, batch_data in enumerate(batches, 1):
            # Create description_id-based sentences for translation
            id_sentences = "\n".join([
                f"{description_id}. {sentence}"
                for description_id, sentence in batch_data
            ])
            prefix = custom_id_prefix if custom_id_prefix else os.path.splitext(
                os.path.basename(csv_filename))[0]
            json_entry = {
                "custom_id": f"{prefix}-batch-{batch_num:04d}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model":
                    model_name,
                    "messages": [{
                        "role": "system",
                        "content": system_prompt
                    }, {
                        "role": "user",
                        "content": id_sentences
                    }],
                    "temperature":
                    0,
                    "max_tokens":
                    token_limit
                }
            }
            jsonl_file.write(json.dumps(json_entry, ensure_ascii=False) + '\n')

    print(
        f"Created JSONL file for {csv_filename} with {len(data_rows)} sentences across {len(batches)} batches (token-based)"
    )


def process_folder_of_csvs(input_folder, output_folder, target_language):
    """
    Process all CSV files in input_folder, outputting a separate JSONL per input file in output_folder.
    """
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    csv_files = [
        f for f in os.listdir(input_folder) if f.lower().endswith('.csv')
    ]
    if not csv_files:
        print(f"No CSV files found in {input_folder}")
        return
    for csv_file in csv_files:
        input_path = os.path.join(input_folder, csv_file)
        base_name = os.path.splitext(csv_file)[0]
        output_path = os.path.join(output_folder, f"{base_name}.jsonl")
        create_jsonl_from_csv(input_path,
                              output_path,
                              target_language,
                              custom_id_prefix=base_name)
    print(
        f"Processed {len(csv_files)} CSV files from {input_folder} to {output_folder}"
    )


# Example usage:
if __name__ == "__main__":
    if len(sys.argv) == 4:
        # Single file mode
        csv_file = sys.argv[1]
        jsonl_file = sys.argv[2]
        target_language = sys.argv[3]
        create_jsonl_from_csv(csv_file, jsonl_file, target_language)
    elif len(sys.argv) == 5 and sys.argv[1] == '--folder':
        # Folder mode
        input_folder = sys.argv[2]
        output_folder = sys.argv[3]
        target_language = sys.argv[4]
        process_folder_of_csvs(input_folder, output_folder, target_language)
    else:
        print("Usage:")
        print(
            "  Single file: python jsonl_convertor.py <input_csv> <output_jsonl> <target_language>"
        )
        print(
            "  Folder:      python jsonl_convertor.py --folder <input_folder> <output_folder> <target_language>"
        )
        print("Example:")
        print(
            "  python jsonl_convertor.py test_input.csv test_output.jsonl Hindi"
        )
        print(
            "  python jsonl_convertor.py --folder input_folder output_folder Hindi"
        )
        sys.exit(1)
