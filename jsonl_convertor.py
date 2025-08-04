import csv
import json


def create_jsonl_from_csv(csv_filename, jsonl_filename, batch_size=50):
    """
    Create JSONL file from CSV with description_id support.
    CSV format: description_id, name (English sentence)
    """
    with open(csv_filename, 'r', encoding='utf-8') as csv_file:
        reader = csv.reader(csv_file)
        next(reader)  # Skip the header row

        # Store both description_id and sentence
        data_rows = []
        for row in reader:
            if len(row) > 1 and row[1].strip():
                description_id = row[0].strip()
                sentence = row[1].strip()
                data_rows.append((description_id, sentence))

    system_prompt = """You are an expert automotive translator proficient in English and Telugu. Your task is to translate technical automotive sentences from English into accurate, formal Telugu. Ensure technical automotive terminology is translated precisely. If a specific automotive technical term, diagnostic code, or component name doesn't have an exact Telugu equivalent, retain it in English or transliterate it clearly into Telugu script.
- 
- Preserve numeric codes, such as fault codes (e.g., P0089), as-is.
- The sentences provided by the user are numbered. Provide translations in Telugu strictly following the exact numbering and sequence of the input sentences. Do not alter the sequence under any circumstance.
- Only output translated sentences in Telugu with the respective numbering. Do NOT include explanations or additional text.

Example:
Input:
1. The fault code P0089 indicates that there is an issue with the performance of the fuel pressure regulator 1. This may cause a decrease in fuel efficiency, difficulty starting the engine, or poor engine performance.
2. Engine misfire can occur due to issues with the ignition coils or spark plugs.

Expected Output:
1. ఫాల్ట్ కోడ్ P0089 ఫ్యూయల్ ప్రెషర్ రెగ్యులేటర్ 1 పనితీరులో సమస్య ఉన్నట్లు సూచిస్తుంది. దీని వల్ల ఇంధన సామర్థ్యం తగ్గడం, ఇంజిన్ స్టార్ట్ చేయడంలో ఇబ్బందులు, లేదా ఇంజిన్ పనితీరు బలహీనపడవచ్చు.
2. ఇగ్నిషన్ కాయిల్స్ లేదా స్పార్క్ ప్లగ్స్ లో సమస్యల వల్ల ఇంజిన్ మిస్‌ఫైర్ సంభవించవచ్చు."""

    with open(jsonl_filename, 'w', encoding='utf-8') as jsonl_file:
        for i in range(0, len(data_rows), batch_size):
            batch_data = data_rows[i:i + batch_size]

            # Create numbered sentences for translation
            numbered_sentences = "\n".join([
                f"{idx+1}. {sentence}"
                for idx, (description_id, sentence) in enumerate(batch_data)
            ])

            json_entry = {
                "custom_id": f"batch-{i // batch_size + 1:04d}",
                "method": "POST",
                "url": "/v1/chat/completions",
                "body": {
                    "model":
                    "gpt-4o",
                    "messages": [{
                        "role": "system",
                        "content": system_prompt
                    }, {
                        "role": "user",
                        "content": numbered_sentences
                    }],
                    "temperature":
                    0,
                    "max_tokens":
                    16000
                }
            }

            jsonl_file.write(json.dumps(json_entry, ensure_ascii=False) + '\n')

    print(
        f"Created JSONL file with {len(data_rows)} sentences across {(len(data_rows) + batch_size - 1) // batch_size} batches"
    )


# Example usage:
if __name__ == "__main__":
    create_jsonl_from_csv('generic-codes-symptoms - generic-codes-symptoms.csv',
                          'batch_requests.jsonl',
                          batch_size=50)
