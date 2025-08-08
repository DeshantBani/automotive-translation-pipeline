# Error Analysis Tool Documentation

## Overview

The Error Analysis Tool provides comprehensive analysis of JSONL translation output files, identifying various types of errors including JSON parsing issues, missing translations, suspicious translations, and API response problems.

## Features

- **JSON Parse Error Detection**: Identifies batches where the AI response couldn't be parsed as valid JSON
- **Suspicious Translation Detection**: Flags translations that appear to be placeholders, incomplete, or malformed
- **Missing Translation Analysis**: Compares against original input to identify missing translations (when input CSV provided)
- **HTTP Status Error Detection**: Identifies API response errors and rate limiting issues
- **Response Format Validation**: Detects malformed API responses
- **Detailed Error Logging**: Creates comprehensive error logs with timestamps and detailed information
- **Success Rate Calculation**: Provides overall translation pipeline success metrics

## Usage Methods

### Method 1: Integrated with auto_translate.py

```bash
# Analyze JSONL file only
python auto_translate.py analyze output.jsonl

# Analyze with input comparison
python auto_translate.py analyze output.jsonl input.csv
```

### Method 2: Standalone error_analyzer.py

```bash
# Basic analysis
python error_analyzer.py output.jsonl

# With input comparison
python error_analyzer.py output.jsonl --input input.csv

# With custom error log path
python error_analyzer.py output.jsonl --log custom_errors.log

# Verbose output (shows detailed errors)
python error_analyzer.py output.jsonl --verbose
```

## Command Line Options (error_analyzer.py)

- `jsonl_file`: Path to the JSONL output file to analyze (required)
- `--input`, `-i`: Optional path to original input CSV for comparison
- `--log`, `-l`: Optional path for error log file (auto-generated if not provided)
- `--verbose`, `-v`: Show detailed error information in console output

## Error Types Detected

### 1. JSON Parse Errors

- **Description**: Batches where the AI response couldn't be parsed as valid JSON
- **Common Causes**:
  - Incomplete JSON responses
  - Markdown formatting issues
  - Unicode encoding problems
  - Truncated responses
- **Example**: Response contains ````json` markers but malformed JSON content

### 2. Suspicious Translations

- **Description**: Translations that appear to be placeholders or incomplete
- **Detection Criteria**:
  - Very short translations (< 3 characters)
  - Common placeholder text patterns
  - Pure numbers as translations
  - System-related keywords
- **Examples**: "[TRANSLATION_FAILED]", "null", "error", pure numeric values

### 3. Empty Responses

- **Description**: API responses with no content
- **Common Causes**:
  - API rate limiting
  - Token limit exceeded
  - Model processing errors

### 4. HTTP Status Errors

- **Description**: Non-200 HTTP status codes from the API
- **Common Status Codes**:
  - 429: Rate limiting
  - 500: Internal server error
  - 400: Bad request

### 5. Response Format Errors

- **Description**: API responses missing expected structure
- **Common Issues**:
  - Missing `response.body.choices[0].message.content` path
  - Unexpected response format

## Output Files

### Error Log File

- **Location**: Auto-generated with timestamp (e.g., `error_analysis_output_20250807_182630.log`)
- **Contents**:
  - Detailed timestamped error entries
  - Content previews of failed batches
  - Comprehensive summary statistics
  - Specific error details for each batch

### Console Output

- **Summary Statistics**: Success rate, error counts by type
- **Detailed Errors**: (when --verbose flag used)
- **Recommendations**: Based on error patterns detected

## Analysis Results Structure

The `analyze_jsonl_errors()` function returns a dictionary with:

```python
{
    'total_batches': int,
    'successful_batches': int,
    'failed_batches': int,
    'json_parse_errors': [list of error objects],
    'suspicious_translations': [list of error objects],
    'empty_responses': [list of error objects],
    'status_code_errors': [list of error objects],
    'response_format_errors': [list of error objects],
    'summary': {
        'total_batches': int,
        'successful_batches': int,
        'failed_batches': int,
        'success_rate_percentage': float,
        'json_parse_errors_count': int,
        'suspicious_translations_count': int,
        'empty_responses_count': int,
        'status_code_errors_count': int,
        'response_format_errors_count': int
    }
}
```

## Example Error Objects

### JSON Parse Error

````python
{
    'batch_id': 'batch-0003',
    'line_number': 3,
    'content_preview': '```json\n{\n    "8092": "translation"...',
    'content_length': 16911,
    'parse_error': 'Failed to extract any translations'
}
````

### Suspicious Translation

```python
{
    'batch_id': 'batch-0001',
    'description_id': '4425',
    'translation': '[TRANSLATION_FAILED]',
    'original_text': 'Engine Control Module detects...',
    'reason': 'Suspicious translation pattern'
}
```

### HTTP Status Error

```python
{
    'batch_id': 'batch-0002',
    'status_code': 429,
    'line_number': 2,
    'error_details': 'Rate limit exceeded'
}
```

## Success Rate Interpretation

- **90%+ Success Rate**: ✅ Excellent - Minor issues acceptable
- **75-89% Success Rate**: ⚠️ Good - Some issues to address
- **50-74% Success Rate**: ⚠️ Moderate - Review and fix parsing issues
- **<50% Success Rate**: ❌ Low - Significant issues need attention

## Common Troubleshooting

### High JSON Parse Errors

1. Check if responses contain markdown formatting
2. Review content previews in error log
3. Consider improving JSON cleanup strategies in `auto_translate.py`

### High Suspicious Translation Rate

1. Review translation quality settings
2. Check for incomplete model responses
3. Verify technical terminology handling

### HTTP Status Errors

1. Check API rate limits and quotas
2. Review request timing and batch sizes
3. Monitor API service status

## Integration with Translation Pipeline

The error analysis tool is designed to work seamlessly with the existing translation pipeline:

1. **Post-Translation Analysis**: Run after batch translation completes
2. **Debugging Failed Batches**: Identify specific batches that need reprocessing
3. **Quality Assurance**: Validate translation output before final delivery
4. **Pipeline Optimization**: Use error patterns to improve batch processing strategies

## Files Created

1. **Error Log**: Timestamped detailed error analysis
2. **Console Output**: Summary and recommendations
3. **Return Data**: Structured error analysis results for programmatic use

This tool provides essential quality control and debugging capabilities for the automated translation pipeline, enabling quick identification and resolution of translation issues.
