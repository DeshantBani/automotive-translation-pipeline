#!/bin/bash

# Quick GitHub Update Script
# Simple script for fast commits and pushes

echo "🚀 Quick GitHub Update..."

# Clean up temporary files
rm -f missing_translations_*.log
find . -name ".DS_Store" -delete

# Add all important files
git add *.py *.md .gitignore

# Quick commit with timestamp
current_time=$(date '+%Y-%m-%d %H:%M:%S')
git commit -m "update: automatic commit on $current_time

- Updated translation pipeline code
- Cleaned up temporary files
- Auto-generated commit"

# Push to current branch
git push origin $(git branch --show-current)

echo "✅ Quick update complete!"
