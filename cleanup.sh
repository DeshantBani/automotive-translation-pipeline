#!/bin/bash

# Cleanup Script for Translation Project
# Removes all temporary, generated, and cache files

echo "🧹 Cleaning up translation project files..."

# Remove missing translations logs
echo "Removing missing translations logs..."
rm -f missing_translations_*.log

# Remove error analysis logs
echo "Removing error analysis logs..."
rm -f error_analysis_*.log

# Remove system files
echo "Removing system files..."
find . -name ".DS_Store" -delete
find . -name "Thumbs.db" -delete

# Remove Python cache
echo "Removing Python cache..."
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null

# Remove temporary batch files (keep structure but clean contents)
echo "Cleaning batch files..."
rm -f *_batch.jsonl *_output.jsonl *_errors.jsonl *_repaired.jsonl

# Remove temporary CSV files
echo "Removing temporary CSV files..."
rm -f output_test.csv
rm -f corrected_translated_output.csv
rm -f final_translated_output.csv
rm -f sorted_filtered.csv

# Clean logs directory but keep the directory
if [ -d "logs" ]; then
    echo "Cleaning logs directory..."
    rm -f logs/*.txt logs/*.log
fi

# Clean jsonl directory but keep the directory
if [ -d "jsonl" ]; then
    echo "Cleaning jsonl directory..."
    rm -f jsonl/*.jsonl
fi

# Clean output_folder but keep the directory
if [ -d "output_folder" ]; then
    echo "Cleaning output_folder..."
    rm -f output_folder/*.csv output_folder/*.jsonl output_folder/*.txt
fi

# Clean translation_folder but keep the directory
if [ -d "translation_folder" ]; then
    echo "Cleaning translation_folder..."
    rm -f translation_folder/*.csv
fi

# Reset batch tracking
echo "Resetting batch tracking..."
if [ -f "batch_job_tracking.csv" ]; then
    echo "batch_id,input_file,job_id,status,timestamp,target_language,output_file" > batch_job_tracking.csv
fi

echo "✅ Cleanup complete!"
echo ""
echo "📊 Directory sizes after cleanup:"
du -h logs/ jsonl/ output_folder/ translation_folder/ 2>/dev/null || echo "Directories cleaned or don't exist"
