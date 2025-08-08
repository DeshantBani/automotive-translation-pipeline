#!/usr/bin/env python3
"""
Test the parsing function for the new JSON format
"""

import json
import re


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


def split_translations_by_id(translated_blob):
    """Extract translations by description_id from JSON format."""
    if not translated_blob:
        return {}

    translations = {}

    try:
        # First try to parse as JSON (new format)
        json_data = json.loads(translated_blob.strip())
        if isinstance(json_data, dict):
            # Direct JSON mapping - this is what we want
            for desc_id, translation in json_data.items():
                if translation and str(translation).strip():
                    translations[str(desc_id)] = str(translation).strip()
            return translations
    except json.JSONDecodeError:
        # If JSON parsing fails, fall back to line-by-line parsing
        print("JSON parsing failed, falling back to line-by-line parsing")

    # Fallback: Parse line by line (for backward compatibility)
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

                # Clean up translation (remove quotes if present)
                translation = translation.strip().strip('"').strip("'")

                # Only add if translation is not empty and not suspicious
                if translation and not is_suspicious_translation(translation):
                    translations[description_id] = translation
                matched = True
                break

        if not matched and l:
            print(f"Warning: Could not parse line: {l[:100]}...")

    return translations


def test_parsing():
    """Test the parsing function with different formats"""

    # Test 1: Perfect JSON format (what we want)
    print("=== TEST 1: Perfect JSON Format ===")
    perfect_json = '''{"21": "ఫ్యూయల్ డెలివరీ ప్రెజర్ సెన్సార్ వద్ద తక్కువ ఇంధన పీడనం గుర్తించబడింది", "27": "ఇంటేక్ ఎయిర్ టెంపరేచర్ (IAT) సెన్సార్ పనితీరు లోపం గుర్తించబడింది", "838": "రేఖాంశ యాక్సిలరేషన్ సరిహద్దు మించిపోయింది", "965": "ఇగ్నిషన్ రన్/యాక్ట్ సర్క్యూట్ ఓపెన్"}'''

    result1 = split_translations_by_id(perfect_json)
    print(f"Parsed {len(result1)} translations:")
    for k, v in result1.items():
        print(f"  {k}: {v[:50]}...")

    # Test 2: Old desc_ format (fallback)
    print("\n=== TEST 2: Old desc_ Format (Fallback) ===")
    old_format = '''desc_21. ఫ్యూయల్ డెలివరీ ప్రెజర్ సెన్సార్ వద్ద తక్కువ ఇంధన పీడనం గుర్తించబడింది
desc_27. ఇంటేక్ ఎయిర్ టెంపరేచర్ (IAT) సెన్సార్ పనితీరు లోపం గుర్తించబడింది
desc_838. డెక్ లిడ్ రిలీస్ సర్క్యూట్ బ్యాటరీకి షార్ట్
desc_965. PATS ట్రాన్సీవర్ మాడ్యూల్ సిగ్నల్ అందలేదు'''

    result2 = split_translations_by_id(old_format)
    print(f"Parsed {len(result2)} translations:")
    for k, v in result2.items():
        print(f"  {k}: {v[:50]}...")

    # Test 3: Tuple format (fallback)
    print("\n=== TEST 3: Tuple Format (Fallback) ===")
    tuple_format = '''320. ('640', 'ఎయిర్ సస్పెన్షన్ ఫ్రంట్ హైట్ సెన్సార్ హై (SE) సంకేతం సర్క్యూట్ లోపం')
321. ('641', 'ఎయిర్ సస్పెన్షన్ ఫ్రంట్ హైట్ సెన్సార్ హై (SE) సంకేతం సర్క్యూట్ ఓపెన్')'''

    result3 = split_translations_by_id(tuple_format)
    print(f"Parsed {len(result3)} translations:")
    for k, v in result3.items():
        print(f"  {k}: {v[:50]}...")


if __name__ == "__main__":
    test_parsing()
