# Batch Job Tracking System

## Overview

The enhanced translation pipeline now includes comprehensive batch job tracking functionality that automatically maintains a CSV database of all translation jobs with their status and details.

## Features

### 📊 **Automatic Tracking**

- Every translation job is automatically recorded
- No manual intervention required
- Persistent storage across pipeline runs

### 📝 **Comprehensive Records**

Each batch record includes:

- **batch_id**: Unique identifier for the batch
- **input_file**: Path to the source CSV file
- **job_id**: OpenAI batch job identifier
- **status**: Current job status (submitted, completed, failed, etc.)
- **timestamp**: Unix timestamp of job submission
- **target_language**: Translation target language
- **output_file**: Path to the final translated CSV

### 🔄 **Status Updates**

- Automatic status updates throughout pipeline
- Real-time tracking of job progression
- Final status recording upon completion

### 🛠️ **Management Tools**

- Command-line utility for viewing and managing records
- Filtering by status, language, or date
- Summary statistics and reporting

## File Structure

### Tracking File

- **Location**: `batch_job_tracking.csv`
- **Format**: Standard CSV with headers
- **Encoding**: UTF-8 for international language support

### Example Record

```csv
batch_id,input_file,job_id,status,timestamp,target_language,output_file
input_test5_1754566353,input_folder/input_test5.csv,batch_68948ed326b481909377bad8a11e27a8,completed,1754566353,Telugu,translation_folder/input_test5_translated.csv
```

## Usage

### Automatic Tracking

Tracking happens automatically when you run the translation pipeline:

```bash
python auto_translate.py input.csv Telugu output.csv
```

**What gets recorded:**

1. **Initial submission**: `batch_id`, `input_file`, `job_id`, `status=submitted`
2. **Status updates**: As job progresses through OpenAI's system
3. **Completion**: Final status and output file path

### Manual Management

Use the `batch_tracker.py` utility for viewing and managing records:

#### List All Batches

```bash
python batch_tracker.py list
```

#### Filter by Status

```bash
python batch_tracker.py status completed
python batch_tracker.py status failed
python batch_tracker.py status submitted
```

#### View Batch Details

```bash
python batch_tracker.py details <job_id>
```

#### Summary Statistics

```bash
python batch_tracker.py summary
```

## Utility Commands

### `batch_tracker.py list`

Shows all batch records in a formatted table:

```
=== ALL BATCH RECORDS ===
batch_id               | input_file           | job_id                 | status    | formatted_time      | target_language
--------------------------------------------------------------------------------------------------------
input_test5_1754566353 | input_test5.csv      | batch_68948ed326b4... | completed | 2025-08-07 17:02:33 | Telugu
input_test4_1754564244 | input_test4.csv      | batch_689486961b58... | completed | 2025-08-07 16:27:24 | Telugu

Total records: 2
```

### `batch_tracker.py summary`

Provides overview statistics:

```
=== BATCH TRACKING SUMMARY ===
Total batches: 5

Status breakdown:
  completed: 4
  failed: 1

Language breakdown:
  Telugu: 4
  Hindi: 1

Recent activity (last 5):
  1. input_test5_1754566353 (completed) - 2025-08-07 17:02:33
  2. input_test4_1754564244 (completed) - 2025-08-07 16:27:24
```

### `batch_tracker.py status <status>`

Filter records by specific status:

```bash
python batch_tracker.py status completed  # Show only completed jobs
python batch_tracker.py status failed     # Show only failed jobs
python batch_tracker.py status submitted  # Show jobs in progress
```

### `batch_tracker.py details <job_id>`

Show detailed information for a specific batch:

```bash
python batch_tracker.py details batch_68948ed326b481909377bad8a11e27a8
```

Output:

```
=== BATCH DETAILS FOR JOB ID: batch_68948ed326b481909377bad8a11e27a8 ===
Batch ID:        input_test5_1754566353
Input File:      input_folder/input_test5.csv
Job ID:          batch_68948ed326b481909377bad8a11e27a8
Status:          completed
Timestamp:       2025-08-07 17:02:33
Target Language: Telugu
Output File:     translation_folder/input_test5_translated.csv
```

## Status Values

### Standard Statuses

- **`submitted`**: Job submitted to OpenAI, waiting to start
- **`validating`**: OpenAI is validating the input
- **`in_progress`**: Translation is actively running
- **`finalizing`**: OpenAI is preparing final results
- **`completed`**: Translation completed successfully
- **`failed`**: Job failed (check error logs)

### Error Statuses

- **`download_failed`**: Results available but download failed
- **`unknown_<status>`**: Unexpected status from OpenAI

## Integration with Logging

The batch tracking system integrates seamlessly with the logging system:

```
2025-08-07 17:45:12 - INFO - Created new batch tracking file: batch_job_tracking.csv
2025-08-07 17:45:16 - INFO - Added batch record: input_test5_1754566353 -> batch_68948ed326b4... (submitted)
2025-08-07 17:52:10 - INFO - Updated batch record: batch_68948ed326b4... -> completed
```

## Data Persistence

### Append-Only Design

- New records are always appended to the CSV file
- No data loss from concurrent runs
- Historical record of all translation activities

### Safe Updates

- Status updates modify existing records in place
- Atomic file operations prevent corruption
- Backup and recovery friendly

## Use Cases

### 📊 **Project Management**

- Track translation progress across multiple files
- Monitor job completion rates
- Identify patterns in failed jobs

### 🔍 **Debugging**

- Correlate job IDs between local logs and OpenAI
- Identify which input files cause issues
- Track timing and performance metrics

### 📋 **Reporting**

- Generate reports for clients or management
- Historical analysis of translation volumes
- Language-specific success rates

### 🔄 **Workflow Optimization**

- Identify optimal batch sizes
- Monitor processing times
- Plan resource allocation

## File Management

### Regular Maintenance

The tracking file will grow over time. Consider periodic maintenance:

```bash
# Archive old records (example)
head -n 1 batch_job_tracking.csv > headers.csv
tail -n +2 batch_job_tracking.csv | head -n -100 >> archive_$(date +%Y%m%d).csv
tail -n 100 batch_job_tracking.csv >> headers.csv
mv headers.csv batch_job_tracking.csv
```

### Backup Strategy

```bash
# Daily backup
cp batch_job_tracking.csv "backup/batch_tracking_$(date +%Y%m%d).csv"
```

## Error Handling

### Missing Tracking File

If the tracking file is accidentally deleted, it will be automatically recreated on the next translation run.

### Corrupted Records

The system is resilient to minor CSV formatting issues and will continue operation even with some corrupted records.

### Concurrent Access

The append-only design minimizes issues with multiple processes accessing the file simultaneously.

## Advanced Usage

### Custom Queries

You can directly query the CSV file using standard tools:

```bash
# Count completed jobs
grep ",completed," batch_job_tracking.csv | wc -l

# Find all Telugu translations
grep ",Telugu," batch_job_tracking.csv

# Show recent jobs (last 24 hours)
awk -v since=$(date -d '1 day ago' +%s) -F, '$5 > since' batch_job_tracking.csv
```

### Data Analysis

Import into spreadsheet applications or data analysis tools for advanced reporting and visualization.

The batch tracking system provides complete visibility into your translation pipeline operations while requiring zero additional effort from users.
