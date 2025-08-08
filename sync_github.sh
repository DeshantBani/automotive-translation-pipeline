#!/bin/bash

# Simple GitHub sync script to handle divergent branches
echo "🔄 Syncing with GitHub repository..."

# Get current branch
current_branch=$(git branch --show-current)
echo "Current branch: $current_branch"

# Option 1: Rebase approach (recommended)
echo "1. Attempting rebase (recommended)..."
git pull --rebase origin $current_branch

if [ $? -eq 0 ]; then
    echo "✅ Rebase successful! Pushing changes..."
    git push origin $current_branch
    if [ $? -eq 0 ]; then
        echo "🎉 Successfully synced with remote repository!"
    else
        echo "❌ Push failed after successful rebase"
    fi
else
    echo "⚠️  Rebase failed or had conflicts"
    echo ""
    echo "2. Trying merge approach..."
    git config pull.rebase false
    git pull origin $current_branch
    
    if [ $? -eq 0 ]; then
        echo "✅ Merge successful! Pushing changes..."
        git push origin $current_branch
        if [ $? -eq 0 ]; then
            echo "🎉 Successfully synced with remote repository!"
        else
            echo "❌ Push failed after merge"
        fi
    else
        echo "❌ Both rebase and merge failed"
        echo "Manual resolution required:"
        echo "1. Check git status: git status"
        echo "2. Resolve conflicts if any"
        echo "3. Continue rebase: git rebase --continue"
        echo "4. Or abort and try: git rebase --abort"
    fi
fi
