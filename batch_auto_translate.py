#!/usr/bin/env python3
"""
Batch Automated Translation Pipeline
Processes multiple CSV files automatically using auto_translate.py
"""

import os
import sys
import subprocess
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading


def run_single_translation(input_csv, target_language, output_dir):
    """Run auto_translate.py for a single CSV file."""
    try:
        # Create output filename based on input
        input_stem = Path(input_csv).stem
        output_csv = os.path.join(output_dir, f"{input_stem}_translated.csv")

        print(f"\n{'='*60}")
        print(f"Processing: {input_csv}")
        print(f"Output: {output_csv}")
        print(f"{'='*60}")

        # Run auto_translate.py
        cmd = [
            sys.executable, "auto_translate.py", input_csv, target_language,
            output_csv
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=7200  # 2 hour timeout per file
        )

        if result.returncode == 0:
            print(f"✅ SUCCESS: {input_csv} -> {output_csv}")
            return {
                'file': input_csv,
                'status': 'success',
                'output': output_csv,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        else:
            print(f"❌ FAILED: {input_csv}")
            print(f"Error: {result.stderr}")
            return {
                'file': input_csv,
                'status': 'failed',
                'error': result.stderr,
                'stdout': result.stdout
            }

    except subprocess.TimeoutExpired:
        print(f"⏰ TIMEOUT: {input_csv} (took longer than 2 hours)")
        return {
            'file': input_csv,
            'status': 'timeout',
            'error': 'Process timed out after 2 hours'
        }
    except Exception as e:
        print(f"💥 ERROR: {input_csv} - {str(e)}")
        return {'file': input_csv, 'status': 'error', 'error': str(e)}


def process_folder(input_folder,
                   target_language,
                   output_folder,
                   max_workers=3):
    """Process all CSV files in a folder."""

    # Create output directory
    os.makedirs(output_folder, exist_ok=True)

    # Find all CSV files
    csv_files = []
    for file in os.listdir(input_folder):
        if file.lower().endswith('.csv'):
            csv_files.append(os.path.join(input_folder, file))

    if not csv_files:
        print(f"No CSV files found in {input_folder}")
        return

    print(f"Found {len(csv_files)} CSV files to process:")
    for csv_file in csv_files:
        print(f"  - {os.path.basename(csv_file)}")

    # Process files with threading
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(run_single_translation, csv_file, target_language, output_folder):
            csv_file
            for csv_file in csv_files
        }

        # Collect results as they complete
        for future in as_completed(future_to_file):
            result = future.result()
            results.append(result)

    # Print summary
    print(f"\n{'='*60}")
    print("BATCH PROCESSING SUMMARY")
    print(f"{'='*60}")

    successful = [r for r in results if r['status'] == 'success']
    failed = [r for r in results if r['status'] != 'success']

    print(f"✅ Successful: {len(successful)}/{len(results)}")
    print(f"❌ Failed: {len(failed)}/{len(results)}")

    if successful:
        print(f"\nSuccessful translations:")
        for result in successful:
            print(
                f"  - {os.path.basename(result['file'])} -> {os.path.basename(result['output'])}"
            )

    if failed:
        print(f"\nFailed translations:")
        for result in failed:
            print(
                f"  - {os.path.basename(result['file'])}: {result.get('error', 'Unknown error')}"
            )

    # Save detailed log
    log_file = os.path.join(output_folder,
                            f"batch_translation_log_{int(time.time())}.txt")
    with open(log_file, 'w') as f:
        f.write("BATCH TRANSLATION LOG\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Input folder: {input_folder}\n")
        f.write(f"Output folder: {output_folder}\n")
        f.write(f"Target language: {target_language}\n")
        f.write(f"Total files: {len(results)}\n")
        f.write(f"Successful: {len(successful)}\n")
        f.write(f"Failed: {len(failed)}\n\n")

        for result in results:
            f.write(f"File: {result['file']}\n")
            f.write(f"Status: {result['status']}\n")
            if result['status'] == 'success':
                f.write(f"Output: {result['output']}\n")
            else:
                f.write(f"Error: {result.get('error', 'Unknown')}\n")
            f.write("-" * 30 + "\n")

    print(f"\nDetailed log saved to: {log_file}")
    print(f"All outputs saved to: {output_folder}")


def main():
    if len(sys.argv) != 4:
        print(
            "Usage: python batch_auto_translate.py <input_folder> <target_language> <output_folder>"
        )
        print(
            "Example: python batch_auto_translate.py input_csvs Hindi output_translations"
        )
        print(
            "\nThis will process all CSV files in the input folder and save results to the output folder."
        )
        sys.exit(1)

    input_folder = sys.argv[1]
    target_language = sys.argv[2]
    output_folder = sys.argv[3]

    if not os.path.exists(input_folder):
        print(f"Error: Input folder '{input_folder}' does not exist.")
        sys.exit(1)

    print(f"Starting batch translation...")
    print(f"Input folder: {input_folder}")
    print(f"Target language: {target_language}")
    print(f"Output folder: {output_folder}")

    # Process all files
    process_folder(input_folder, target_language, output_folder)


if __name__ == "__main__":
    main()
