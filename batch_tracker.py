#!/usr/bin/env python3
"""
Batch Job Tracking Utility
Provides commands to view and manage batch job tracking records.
"""

import sys
import csv
from pathlib import Path
from datetime import datetime
from auto_translate import list_batch_records, get_batch_record, BATCH_TRACKING_FILE


def print_table(records, headers):
    """Print records in a nice table format."""
    if not records:
        print("No records found.")
        return

    # Calculate column widths
    widths = {}
    for header in headers:
        widths[header] = max(
            len(header),
            max(len(str(record.get(header, ''))) for record in records))

    # Print header
    header_row = " | ".join(f"{header:<{widths[header]}}"
                            for header in headers)
    print(header_row)
    print("-" * len(header_row))

    # Print records
    for record in records:
        row = " | ".join(f"{str(record.get(header, '')):<{widths[header]}}"
                         for header in headers)
        print(row)


def format_timestamp(timestamp_str):
    """Convert timestamp to readable format."""
    try:
        timestamp = int(timestamp_str)
        return datetime.fromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return timestamp_str


def list_all_batches():
    """List all batch records."""
    print("=== ALL BATCH RECORDS ===")
    records = list_batch_records()

    # Add formatted timestamp
    for record in records:
        record['formatted_time'] = format_timestamp(record['timestamp'])

    headers = [
        'batch_id', 'input_file', 'job_id', 'status', 'formatted_time',
        'target_language'
    ]
    print_table(records, headers)
    print(f"\nTotal records: {len(records)}")


def list_by_status(status):
    """List batch records filtered by status."""
    print(f"=== BATCH RECORDS WITH STATUS: {status.upper()} ===")
    records = list_batch_records(status_filter=status)

    # Add formatted timestamp
    for record in records:
        record['formatted_time'] = format_timestamp(record['timestamp'])

    headers = [
        'batch_id', 'input_file', 'job_id', 'status', 'formatted_time',
        'target_language'
    ]
    print_table(records, headers)
    print(f"\nRecords with status '{status}': {len(records)}")


def show_batch_details(job_id):
    """Show detailed information for a specific batch."""
    print(f"=== BATCH DETAILS FOR JOB ID: {job_id} ===")
    record = get_batch_record(job_id)

    if not record:
        print(f"No batch record found for job ID: {job_id}")
        return

    print(f"Batch ID:        {record['batch_id']}")
    print(f"Input File:      {record['input_file']}")
    print(f"Job ID:          {record['job_id']}")
    print(f"Status:          {record['status']}")
    print(f"Timestamp:       {format_timestamp(record['timestamp'])}")
    print(f"Target Language: {record['target_language']}")
    print(f"Output File:     {record['output_file']}")


def show_summary():
    """Show summary statistics."""
    print("=== BATCH TRACKING SUMMARY ===")
    records = list_batch_records()

    if not records:
        print("No batch records found.")
        return

    # Count by status
    status_counts = {}
    for record in records:
        status = record['status']
        status_counts[status] = status_counts.get(status, 0) + 1

    # Count by language
    language_counts = {}
    for record in records:
        lang = record['target_language']
        language_counts[lang] = language_counts.get(lang, 0) + 1

    print(f"Total batches: {len(records)}")
    print("\nStatus breakdown:")
    for status, count in sorted(status_counts.items()):
        print(f"  {status}: {count}")

    print("\nLanguage breakdown:")
    for lang, count in sorted(language_counts.items()):
        print(f"  {lang}: {count}")

    # Recent activity
    recent_records = sorted(records,
                            key=lambda x: int(x['timestamp']),
                            reverse=True)[:5]
    print(f"\nRecent activity (last 5):")
    for i, record in enumerate(recent_records, 1):
        formatted_time = format_timestamp(record['timestamp'])
        print(
            f"  {i}. {record['batch_id']} ({record['status']}) - {formatted_time}"
        )


def main():
    """Main CLI interface."""
    if len(sys.argv) < 2:
        print("Batch Job Tracking Utility")
        print("\nUsage:")
        print(
            "  python batch_tracker.py list                    # List all batches"
        )
        print(
            "  python batch_tracker.py status <status>         # List batches by status"
        )
        print(
            "  python batch_tracker.py details <job_id>        # Show batch details"
        )
        print(
            "  python batch_tracker.py summary                 # Show summary statistics"
        )
        print("\nExamples:")
        print("  python batch_tracker.py list")
        print("  python batch_tracker.py status completed")
        print("  python batch_tracker.py status failed")
        print(
            "  python batch_tracker.py details batch_6892e935932c819090e1be3f2891e6a3"
        )
        print("  python batch_tracker.py summary")
        return

    command = sys.argv[1].lower()

    # Check if tracking file exists
    if not Path(BATCH_TRACKING_FILE).exists():
        print(f"No batch tracking file found: {BATCH_TRACKING_FILE}")
        print("Run a translation job first to create the tracking file.")
        return

    if command == "list":
        list_all_batches()
    elif command == "status":
        if len(sys.argv) < 3:
            print("Usage: python batch_tracker.py status <status>")
            return
        status = sys.argv[2]
        list_by_status(status)
    elif command == "details":
        if len(sys.argv) < 3:
            print("Usage: python batch_tracker.py details <job_id>")
            return
        job_id = sys.argv[2]
        show_batch_details(job_id)
    elif command == "summary":
        show_summary()
    else:
        print(f"Unknown command: {command}")
        print("Use 'python batch_tracker.py' to see available commands.")


if __name__ == "__main__":
    main()
