# GitHub Management Scripts

This folder contains utility scripts for managing the automotive-translation-pipeline GitHub repository.

## Scripts Overview

### 🚀 `update_github.sh` - Comprehensive Update Script

The main script for updating the GitHub repository with full cleanup and user interaction.

**Features:**
- ✅ Cleans up temporary files automatically
- ✅ Updates .gitignore patterns
- ✅ Interactive commit message input
- ✅ Colored output for better visibility
- ✅ Error handling and status checks
- ✅ Shows staged files before commit

**Usage:**
```bash
./update_github.sh
```

**What it does:**
1. Removes temporary files (missing_translations_*.log, .DS_Store, cache files)
2. Stages important files (.py, .md, .gitignore)
3. Shows what will be committed
4. Prompts for commit message (with intelligent default)
5. Commits and pushes to current branch
6. Provides detailed status updates

---

### ⚡ `quick_update.sh` - Fast Update Script

Quick script for rapid commits without user interaction.

**Features:**
- ✅ Automatic cleanup
- ✅ Timestamp-based commit messages
- ✅ No user input required
- ✅ Fast execution

**Usage:**
```bash
./quick_update.sh
```

**What it does:**
1. Quick cleanup of temporary files
2. Automatic staging of important files
3. Commits with timestamp
4. Pushes to current branch

---

### 🧹 `cleanup.sh` - Project Cleanup Script

Comprehensive cleanup script for removing all temporary and generated files.

**Features:**
- ✅ Removes all log files
- ✅ Cleans Python cache
- ✅ Removes temporary batch files
- ✅ Preserves directory structure
- ✅ Resets batch tracking

**Usage:**
```bash
./cleanup.sh
```

**What it cleans:**
- `missing_translations_*.log`
- `error_analysis_*.log`
- Python cache (`__pycache__`, `*.pyc`)
- System files (`.DS_Store`, `Thumbs.db`)
- Temporary batch files (`*_batch.jsonl`, `*_output.jsonl`)
- Large generated CSV files
- Log directories (but keeps folder structure)

---

## File Patterns Ignored by Git

The updated `.gitignore` excludes these patterns:

### 🔒 Sensitive Files
- `*.env` - Environment variables and API keys
- `openai_api_key.txt`, `api_keys.txt`, `secrets.txt`

### 📁 Generated Data
- `output_folder/`, `translation_folder/`, `input_folder/`, `jsonl/`
- `batch_job_tracking.csv`
- Large CSV files (`sorted_filtered.csv`, `final_translated_output.csv`, etc.)

### 📋 Log Files
- `logs/` directory
- `missing_translations_*.log`
- `error_analysis_*.log`
- `translation_log_*.txt`

### 🔄 Temporary Files
- `*_batch.jsonl`, `*_output.jsonl`, `*_errors.jsonl`
- `*.tmp`, `temp/`
- `debug_*.txt`

### 🐍 Python Files
- `__pycache__/`, `*.pyc`, `*.pyo`
- `.venv/`, `venv/`, `env/`

### 💻 IDE Files
- `.vscode/`, `.idea/`
- `.DS_Store`, `Thumbs.db`

---

## Workflow Examples

### Standard Workflow
```bash
# 1. Make code changes
vim auto_translate.py

# 2. Clean up and update repository
./update_github.sh

# 3. Enter custom commit message when prompted
```

### Quick Development Workflow
```bash
# 1. Make quick changes
vim auto_translate.py

# 2. Quick commit and push
./quick_update.sh
```

### Clean Project Before Major Update
```bash
# 1. Clean everything
./cleanup.sh

# 2. Make changes
vim auto_translate.py

# 3. Comprehensive update
./update_github.sh
```

---

## Script Safety Features

### Error Handling
- ✅ Checks if in git repository
- ✅ Validates git operations
- ✅ Provides clear error messages
- ✅ Exits safely on failures

### File Protection
- ✅ Never commits sensitive files (.env, API keys)
- ✅ Preserves directory structure during cleanup
- ✅ Only removes files matching specific patterns

### User Feedback
- ✅ Colored output for better visibility
- ✅ Progress indicators
- ✅ Summary of actions taken
- ✅ Repository URL and branch information

---

## Troubleshooting

### Permission Issues
```bash
chmod +x *.sh
```

### Git Push Fails
```bash
git pull origin $(git branch --show-current)
./update_github.sh
```

### Large Files Not Ignored
Check if patterns in `.gitignore` match your file names and update accordingly.

---

**Repository:** [automotive-translation-pipeline](https://github.com/DeshantBani/automotive-translation-pipeline)  
**Branch:** development
