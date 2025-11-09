#!/bin/bash
# git-webdiff: webdiff entry script (updated)
# This lets you run "git webdiff"

set -euo pipefail

webdiff_args=()
git_args=()

# Function to show help
show_help() {
    cat << 'EOF'
usage: git-webdiff [-h] [options] [git_args ...]

Web-based git difftool

positional arguments:
  git_args                     Arguments to pass to git difftool

options:
  -h, --help                   show this help message and exit
  --port PORT, -p PORT         Port to serve on (default: random)
  --host HOST                  Host to serve on (default: localhost)
  --root-path PATH             Root path for the application (e.g., /webdiff)
  --timeout MINUTES            Automatically shut down the server after this many minutes (default: 0, no timeout)
  --no-timeout                 Disable automatic timeout (equivalent to --timeout 0)
  --watch SECONDS              Watch for diff changes and enable reload (default: 10 seconds)
  --no-watch                   Disable watch mode (equivalent to --watch 0)
  --unified LINES              Number of unified context lines (default: 8)
  --extra-dir-diff-args ARGS   Extra arguments for directory diff
  --extra-file-diff-args ARGS  Extra arguments for file diff
  --max-diff-width WIDTH       Maximum width for diff display (default: 120)
  --theme THEME                Color theme for syntax highlighting (default: googlecode)
  --max-lines-for-syntax LINES Maximum lines for syntax highlighting (default: 25000)
  --diff-algorithm ALGORITHM   Diff algorithm: myers, minimal, patience, histogram
  --color-insert COLOR         Background color for inserted lines (default: #efe)
  --color-delete COLOR         Background color for deleted lines (default: #fee)
  --color-char-insert COLOR    Background color for inserted characters (default: #cfc)
  --color-char-delete COLOR    Background color for deleted characters (default: #fcc)

Examples:
=========

# Compare working directory with HEAD
git-webdiff

# Compare specific commits
git-webdiff HEAD~3..HEAD

# Compare staged changes
git-webdiff --cached

# Compare specific files
git-webdiff -- path/to/file.txt

# Pass options to webdiff
git-webdiff --theme monokai --max-diff-width 150

Configuration:
=============

To use as default git difftool:
    git config --global diff.tool webdiff
    git config --global difftool.prompt false
    git config --global difftool.webdiff.cmd 'WEBDIFF_AS_DIFFTOOL=1 /path/to/git-webdiff "$LOCAL" "$REMOTE"'

To pass arguments when using as a difftool, you can set WEBDIFF_ARGS.
For example, in your .gitconfig:
[difftool "webdiff"]
    cmd = WEBDIFF_ARGS="--theme monokai" WEBDIFF_AS_DIFFTOOL=1 /path/to/git-webdiff "$LOCAL" "$REMOTE"

Or using an environment variable in your shell profile:
    export WEBDIFF_ARGS="--theme monokai --max-diff-width 150"

The server will run in the foreground. Press Ctrl-C to stop it.
EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_help
            exit 0
            ;;
        -p|--port|--timeout|--watch|--unified|--max-diff-width|--max-lines-for-syntax)
            if [[ -z "$2" || ! "$2" =~ ^[0-9]+$ ]]; then
                echo "Error: $1 requires a numeric argument" >&2
                exit 1
            fi
            webdiff_args+=("$1" "$2")
            shift 2
            ;;
        --host|--root-path|--theme|--diff-algorithm|--color-insert|--color-delete|--color-char-insert|--color-char-delete|--extra-dir-diff-args|--extra-file-diff-args)
            if [[ -z "$2" ]]; then
                echo "Error: $1 requires an argument" >&2
                exit 1
            fi
            webdiff_args+=("$1" "$2")
            shift 2
            ;;
        --no-watch|--no-timeout)
            webdiff_args+=("$1")
            shift
            ;;
        *)
            # All remaining arguments are git arguments
            git_args+=("$1")
            shift
            ;;
    esac
done

# Pass git context for hot reload functionality (environment variables for Python)
export WEBDIFF_GIT_ARGS="$(printf "%q " "${git_args[@]}")"
export WEBDIFF_CWD="$(pwd)"

# First check if we're in a git repository
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo "Error: Not in a git repository"
    exit 1
fi

# Check if there are any differences to show
# We need to handle different cases:
# - No arguments: compare working tree with HEAD
# - --cached: compare index with HEAD
# - Other arguments: pass through to git diff
has_diff=0

if [ ${#git_args[@]} -eq 0 ]; then
    # No arguments - check working tree vs HEAD
    git diff --quiet HEAD 2>/dev/null || has_diff=1
else
    # Has arguments - check with git diff
    git diff --quiet "${git_args[@]}" 2>/dev/null || has_diff=1
fi

if [ $has_diff -eq 0 ]; then
    # No differences found with initial args, but we still start the server
    # because the user can change git args from the UI
    echo "No differences found with initial arguments."
    echo "Starting server anyway - you can change git arguments from the UI."
fi

# Start the webdiff server directly
# The Python server will call git difftool itself and manage the lifecycle
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" && exec uv run -m webdiff.app "${webdiff_args[@]}"
