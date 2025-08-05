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
import csv
import re


def save_batch_job_tracking(batch_id, input_file, job_id, target_language,
                            output_file):
    """Save batch job tracking information to a CSV file."""
    tracking_file = "batch_job_tracking.csv"
    timestamp = int(time.time())

    # Check if tracking file exists
    file_exists = os.path.exists(tracking_file)

    with open(tracking_file, 'a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)

        # Write header if file doesn't exist
        if not file_exists:
            writer.writerow([
                "batch_id", "input_file", "job_id", "status", "timestamp",
                "target_language", "output_file"
            ])

        # Write job tracking info
        writer.writerow([
            batch_id, input_file, job_id, "submitted", timestamp,
            target_language, output_file
        ])


def update_batch_job_status(job_id, status):
    """Update job status in batch tracking file."""
    tracking_file = "batch_job_tracking.csv"

    if not os.path.exists(tracking_file):
        return

    # Read existing data
    rows = []
    with open(tracking_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)
        rows.append(header)

        for row in reader:
            if row[2] == job_id:  # job_id column
                row[3] = status  # status column
            rows.append(row)

    # Write back updated data
    with open(tracking_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(rows)


def view_batch_job_tracking():
    """Display batch job tracking information."""
    tracking_file = "batch_job_tracking.csv"

    if not os.path.exists(tracking_file):
        print("No batch job tracking file found.")
        return

    print("\n" + "=" * 100)
    print("BATCH JOB TRACKING INFORMATION")
    print("=" * 100)

    with open(tracking_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader)

        # Print header
        print(
            f"{'Batch ID':<20} {'Input File':<25} {'Job ID':<20} {'Status':<12} {'Language':<10} {'Output File':<25}"
        )
        print("-" * 112)

        # Print each job
        for row in reader:
            if len(row) >= 7:
                batch_id = row[0] if row[0] else "N/A"
                input_file = os.path.basename(row[1]) if row[1] else "N/A"
                job_id = row[2] if row[2] else "N/A"
                status = row[3] if row[3] else "N/A"
                language = row[5] if row[5] else "N/A"
                output_file = os.path.basename(row[6]) if row[6] else "N/A"

                print(
                    f"{batch_id:<20} {input_file:<25} {job_id:<20} {status:<12} {language:<10} {output_file:<25}"
                )

    print("=" * 100)


def run_single_translation(input_csv, target_language, output_dir, batch_id):
    """Run auto_translate.py for a single CSV file with batch tracking."""
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

        # Extract job ID from the output (look for "Job ID: batch_xxxxx")
        job_id = "unknown"
        if result.stdout:
            import re
            job_match = re.search(r'Job ID: (batch_[a-zA-Z0-9]+)',
                                  result.stdout)
            if job_match:
                job_id = job_match.group(1)

        # Save batch job tracking
        save_batch_job_tracking(batch_id, input_csv, job_id, target_language,
                                output_csv)

        if result.returncode == 0:
            print(f"✅ SUCCESS: {input_csv} -> {output_csv}")
            update_batch_job_status(job_id, "completed")
            return {
                'file': input_csv,
                'status': 'success',
                'output': output_csv,
                'job_id': job_id,
                'stdout': result.stdout,
                'stderr': result.stderr
            }
        else:
            print(f"❌ FAILED: {input_csv}")
            print(f"Error: {result.stderr}")
            update_batch_job_status(job_id, "failed")
            return {
                'file': input_csv,
                'status': 'failed',
                'error': result.stderr,
                'job_id': job_id,
                'stdout': result.stdout
            }

    except subprocess.TimeoutExpired:
        print(f"⏰ TIMEOUT: {input_csv} (took longer than 2 hours)")
        update_batch_job_status(job_id, "timeout")
        return {
            'file': input_csv,
            'status': 'timeout',
            'error': 'Process timed out after 2 hours',
            'job_id': job_id
        }
    except Exception as e:
        print(f"💥 ERROR: {input_csv} - {str(e)}")
        update_batch_job_status(job_id, "error")
        return {
            'file': input_csv,
            'status': 'error',
            'error': str(e),
            'job_id': job_id
        }


def process_folder(input_folder,
                   target_language,
                   output_folder,
                   max_workers=3):
    """Process all CSV files in a folder with batch tracking."""

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

    # Create batch ID
    batch_id = f"batch_{int(time.time())}"
    print(f"Batch ID: {batch_id}")

    print(f"Found {len(csv_files)} CSV files to process:")
    for csv_file in csv_files:
        print(f"  - {os.path.basename(csv_file)}")

    # Process files with threading
    results = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_file = {
            executor.submit(run_single_translation, csv_file, target_language, output_folder, batch_id):
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
                f"  - {os.path.basename(result['file'])} -> {os.path.basename(result['output'])} (Job ID: {result['job_id']})"
            )

    if failed:
        print(f"\nFailed translations:")
        for result in failed:
            print(
                f"  - {os.path.basename(result['file'])}: {result.get('error', 'Unknown error')} (Job ID: {result['job_id']})"
            )

    # Save detailed log
    log_file = os.path.join(output_folder,
                            f"batch_translation_log_{int(time.time())}.txt")
    with open(log_file, 'w') as f:
        f.write("BATCH TRANSLATION LOG\n")
        f.write("=" * 50 + "\n\n")
        f.write(f"Batch ID: {batch_id}\n")
        f.write(f"Input folder: {input_folder}\n")
        f.write(f"Output folder: {output_folder}\n")
        f.write(f"Target language: {target_language}\n")
        f.write(f"Total files: {len(results)}\n")
        f.write(f"Successful: {len(successful)}\n")
        f.write(f"Failed: {len(failed)}\n\n")

        for result in results:
            f.write(f"File: {result['file']}\n")
            f.write(f"Job ID: {result['job_id']}\n")
            f.write(f"Status: {result['status']}\n")
            if result['status'] == 'success':
                f.write(f"Output: {result['output']}\n")
            else:
                f.write(f"Error: {result.get('error', 'Unknown')}\n")
            f.write("-" * 30 + "\n")

    print(f"\nDetailed log saved to: {log_file}")
    print(f"All outputs saved to: {output_folder}")
    print(f"Batch job tracking saved to: batch_job_tracking.csv")


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--tracking":
        view_batch_job_tracking()
        return

    if len(sys.argv) != 4:
        print(
            "Usage: python batch_auto_translate.py <input_folder> <target_language> <output_folder>"
        )
        print(
            "Example: python batch_auto_translate.py input_csvs Hindi output_translations"
        )
        print(
            "\nTo view batch job tracking: python batch_auto_translate.py --tracking"
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
