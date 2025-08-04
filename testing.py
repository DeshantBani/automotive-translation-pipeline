#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json


def test_unicode_handling():
    # Test string from your JSON output
    test_string = "1. \u0c07\u0c02\u0c27\u0c28 \u0c35\u0c4d\u0c2f\u0c35\u0c38\u0c4d\u0c25 \u0c32\u0c40\u0c15\u0c4d \u0c17\u0c41\u0c30\u0c4d\u0c24\u0c3f\u0c02\u0c1a\u0c2c\u0c21\u0c3f\u0c02\u0c26\u0c3f \u0c1a\u0c3f\u0c28\u0c4d\u0c28 \u0c32\u0c40\u0c15\u0c4d"

    print("=== UNICODE DEBUG TEST ===")
    print(f"Raw string: {repr(test_string)}")
    print(f"Decoded string: {test_string}")
    print(f"Length: {len(test_string)}")

    # Test if it's actual Telugu
    if '\u0c00' <= test_string[3] <= '\u0c7f':  # Telugu Unicode range
        print("✓ This IS valid Telugu Unicode")
    else:
        print("✗ This is NOT Telugu Unicode")

    # Test splitting
    import re
    cleaned = re.sub(r'^\d+\.\s*', '', test_string)
    print(f"After removing numbering: {cleaned}")

    print("\n=== TESTING YOUR ACTUAL FILE ===")
    try:
        with open("batch_output.jsonl", "r", encoding="utf-8") as f:
            line = f.readline()
            if line:
                data = json.loads(line)
                content = data["response"]["body"]["choices"][0]["message"][
                    "content"]
                print(f"First line content: {repr(content)}")
                print(f"Displayed: {content}")

                # Test first translation
                lines = content.split('\n')
                if lines:
                    first_line = lines[0].strip()
                    cleaned_first = re.sub(r'^\d+\.\s*', '', first_line)
                    print(f"First translation cleaned: {cleaned_first}")

    except FileNotFoundError:
        print("batch_output.jsonl not found")
    except Exception as e:
        print(f"Error reading file: {e}")


if __name__ == "__main__":
    test_unicode_handling()
