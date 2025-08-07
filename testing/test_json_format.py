#!/usr/bin/env python3
"""
Test script to validate the new JSON format for translation batches
"""

import json
from auto_translate import get_system_prompt, create_jsonl_from_csv


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
    print(system_prompt)

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


if __name__ == "__main__":
    test_json_format()
