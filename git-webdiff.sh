#!/bin/bash
# git-webdiff: thin wrapper that checks for git repo and passes args to Python
set -e

# Check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "Error: Not in a git repository" >&2
    exit 1
fi

# Get the script directory and original working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL_DIR="$(pwd)"

# Pass current directory as --git-repo and all args to Python
cd "$SCRIPT_DIR" && exec uv run -m webdiff.app --git-repo "$ORIGINAL_DIR" "$@"
