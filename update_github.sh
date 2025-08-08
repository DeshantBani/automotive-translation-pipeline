#!/bin/bash

# GitHub Repository Update Script
# This script handles the complete process of updating the automotive-translation-pipeline repository

echo "🚀 Starting GitHub Repository Update Process..."
echo "================================================"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check if we're in a git repository
if [ ! -d ".git" ]; then
    print_error "Not in a git repository. Please run this from the project root."
    exit 1
fi

# Step 1: Clean up temporary files that shouldn't be committed
print_status "Step 1: Cleaning up temporary files..."

# Remove missing translations logs
rm -f missing_translations_*.log
print_status "Removed missing_translations_*.log files"

# Remove .DS_Store files
find . -name ".DS_Store" -delete
print_status "Removed .DS_Store files"

# Remove any Python cache files
find . -name "*.pyc" -delete
find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null
print_status "Removed Python cache files"

print_success "Cleanup completed"

# Step 2: Check git status
print_status "Step 2: Checking git status..."
git status --porcelain

# Step 3: Add files to staging
print_status "Step 3: Adding files to staging area..."

# Add all Python files
git add *.py
print_status "Added Python files"

# Add documentation
git add *.md
print_status "Added documentation files"

# Add updated .gitignore
git add .gitignore
print_status "Added .gitignore"

# Add any new config files (but not sensitive ones)
git add requirements.txt 2>/dev/null || true

print_success "Files staged successfully"

# Step 4: Show what will be committed
print_status "Step 4: Files staged for commit:"
git diff --cached --name-status

# Step 5: Get commit message from user
echo ""
print_status "Step 5: Creating commit..."
read -p "Enter commit message (or press Enter for default): " commit_message

if [ -z "$commit_message" ]; then
    commit_message="feat: comprehensive GitHub workflow automation and project cleanup

- Added GitHub repository management scripts (update_github.sh, quick_update.sh, cleanup.sh)
- Updated .gitignore with comprehensive patterns for translation project artifacts
- Fixed auto_translate.py execution issues and duplicate function problems
- Added batch tracking, error analysis, and logging guide documentation
- Implemented automated cleanup for temporary files and missing translations logs
- Enhanced translation pipeline with proper error handling and routing"
fi

# Step 6: Commit changes
git commit -m "$commit_message"
if [ $? -eq 0 ]; then
    print_success "Commit created successfully"
else
    print_error "Commit failed"
    exit 1
fi

# Step 7: Pull latest changes and push to remote
print_status "Step 7: Syncing with remote repository..."

# Get current branch
current_branch=$(git branch --show-current)
print_status "Current branch: $current_branch"

# Pull with rebase to avoid merge commits
print_status "Pulling latest changes with rebase..."
git pull --rebase origin $current_branch
if [ $? -ne 0 ]; then
    print_warning "Rebase encountered conflicts or issues"
    print_status "Attempting to continue with current state..."
fi

# Push to remote
print_status "Pushing to origin/$current_branch..."
git push origin $current_branch
if [ $? -eq 0 ]; then
    print_success "Successfully pushed to origin/$current_branch"
else
    print_error "Push failed"
    print_status "Trying force push with lease (safer than force push)..."
    git push --force-with-lease origin $current_branch
    if [ $? -eq 0 ]; then
        print_success "Successfully force-pushed to origin/$current_branch"
    else
        print_error "Force push also failed. Manual intervention may be required."
        exit 1
    fi
fi

# Step 8: Display summary
echo ""
echo "================================================"
print_success "🎉 GitHub Repository Update Complete!"
echo "================================================"
print_status "Summary:"
print_status "- Cleaned up temporary files"
print_status "- Updated .gitignore with new patterns"
print_status "- Committed changes with message: '$commit_message'"
print_status "- Pushed to origin/$current_branch"
echo ""
print_status "Repository URL: https://github.com/DeshantBani/automotive-translation-pipeline"
print_status "Branch: $current_branch"
echo "================================================"
