#!/usr/bin/env python3
"""
Test script to validate the new JSON format for translation batches
"""

import json


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


def test_json_format():
    """Test the new JSON format generation"""

    # Test data
    test_data = [
        ("21",
         "Low fuel pressure detected at the fuel delivery pressure sensor"),
        ("27",
         "A performance fault with the Intake Air Temperature (IAT) sensor detected"
         ), ("838", "Longitudinal Acceleration Threshold Exceeded"),
        ("965", "Ignition Run/Act Circuit Open")
    ]

    # Create JSON format that will be sent to OpenAI
    batch_json = {}
    for description_id, sentence in test_data:
        batch_json[description_id] = sentence

    print("=== NEW JSON FORMAT ===")
    print("Input to OpenAI:")
    print(json.dumps(batch_json, indent=2, ensure_ascii=False))

    print("\n=== SYSTEM PROMPT ===")
    system_prompt = get_system_prompt("Telugu")
    print(system_prompt[:300] + "...")

    print("\n=== EXPECTED OUTPUT FORMAT ===")
    expected_output = {
        "21":
        "ఫ్యూయల్ డెలివరీ ప్రెజర్ సెన్సార్ వద్ద తక్కువ ఇంధన పీడనం గుర్తించబడింది",
        "27":
        "ఇంటేక్ ఎయిర్ టెంపరేచర్ (IAT) సెన్సార్ పనితీరు లోపం గుర్తించబడింది",
        "838": "రేఖాంశ యాక్సిలరేషన్ సరిహద్దు మించిపోయింది",
        "965": "ఇగ్నిషన్ రన్/యాక్ట్ సర్క్యూట్ ఓపెన్"
    }
    print(json.dumps(expected_output, indent=2, ensure_ascii=False))

    print("\n=== COMPARISON WITH OLD FORMAT ===")
    print("OLD desc_ format would be:")
    for desc_id, sentence in test_data:
        print(f"desc_{desc_id}. {sentence}")

    print("\nNEW JSON format:")
    print(json.dumps(batch_json, ensure_ascii=False))


if __name__ == "__main__":
    test_json_format()
