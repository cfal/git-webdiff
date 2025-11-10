#!/bin/bash
# git-webdiff: thin wrapper that checks for git repo and passes args to Python
set -e

# Get the script directory and original working directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORIGINAL_DIR="$(pwd)"

# Check if user specified --git-repo arguments
HAS_GIT_REPO=false
for arg in "$@"; do
    if [[ "$arg" == "--git-repo" ]]; then
        HAS_GIT_REPO=true
        break
    fi
done

# If no --git-repo specified, check we're in a git repo and add current directory
if [ "$HAS_GIT_REPO" = false ]; then
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        echo "Error: Not in a git repository" >&2
        exit 1
    fi
    # Pass current directory as --git-repo and all args to Python
    cd "$SCRIPT_DIR" && exec uv run -m webdiff.app --git-repo "$ORIGINAL_DIR" "$@"
else
    # User specified --git-repo, just pass through all args
    cd "$SCRIPT_DIR" && exec uv run -m webdiff.app "$@"
fi
