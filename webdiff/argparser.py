"""Parse command line arguments to webdiff."""

import argparse
import os
from typing import List, Dict


class UsageError(Exception):
    pass


def parse_git_repo_arg(arg: str) -> Dict[str, str]:
    """Parse --git-repo argument with optional label.

    Examples:
        'frontend:/path/to/repo' -> {'label': 'frontend', 'path': '/path/to/repo'}
        '/path/to/repo' -> {'label': 'repo', 'path': '/path/to/repo'}
    """
    if ':' in arg:
        label, path = arg.split(':', 1)
        return {'label': label, 'path': os.path.abspath(path)}
    else:
        path = os.path.abspath(arg)
        label = os.path.basename(path)
        return {'label': label, 'path': path}


def ensure_unique_labels(repos: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Ensure all repo labels are unique by appending numbers if needed.

    Args:
        repos: List of repo dicts with 'label' and 'path' keys

    Returns:
        List of repos with guaranteed unique labels
    """
    label_counts = {}
    result = []

    for repo in repos:
        original_label = repo['label']
        label = original_label

        if label in label_counts:
            # Label already exists, append number
            count = label_counts[label]
            label = f"{original_label}-{count}"
            label_counts[original_label] = count + 1
        else:
            label_counts[label] = 1

        result.append({'label': label, 'path': repo['path']})

    return result


def validate_single_repo(label: str, path: str) -> tuple:
    """Validate a single repository.

    Args:
        label: Repo label
        path: Repo path

    Returns:
        (is_valid, error_message)
    """
    # 1. Label must be non-empty
    if not label or not label.strip():
        return False, "Label cannot be empty"

    # 2. Label must not contain invalid characters
    if ':' in label:
        return False, "Label cannot contain colon (:)"

    # 3. Path must be absolute
    if not os.path.isabs(path):
        return False, "Path must be absolute"

    # 4. Path must exist
    if not os.path.exists(path):
        return False, "Path does not exist"

    # 5. Path must be a directory
    if not os.path.isdir(path):
        return False, "Path is not a directory"

    # 6. Path must be a git repository
    git_dir = os.path.join(path, '.git')
    if not os.path.exists(git_dir):
        return False, "Path is not a git repository (no .git directory)"

    return True, None


def validate_repo_list(repos: List[Dict[str, str]]) -> tuple:
    """Validate a list of repositories.

    Args:
        repos: List of repo dicts with 'label' and 'path' keys

    Returns:
        (is_valid, error_message)
    """
    # 1. Must have at least one repository
    if len(repos) == 0:
        return False, "Must have at least one repository"

    # 2. No duplicate labels
    labels = [r['label'] for r in repos]
    if len(labels) != len(set(labels)):
        duplicates = [label for label in labels if labels.count(label) > 1]
        return False, f"Duplicate labels: {', '.join(set(duplicates))}"

    # 3. No duplicate paths (normalized)
    paths = [os.path.abspath(r['path']) for r in repos]
    if len(paths) != len(set(paths)):
        return False, "Duplicate paths not allowed"

    # 4. Validate each individual repo
    for repo in repos:
        valid, error = validate_single_repo(repo['label'], repo['path'])
        if not valid:
            return False, f"Invalid repo '{repo['label']}': {error}"

    return True, None


USAGE = """Usage: git-webdiff [options] [git_args ...]

Web-based git diff server for viewing diffs in your browser.

Examples:
  git-webdiff                    # Start server comparing working directory with HEAD
  git-webdiff HEAD~3..HEAD       # Start server comparing specific commits
  git-webdiff --cached           # Start server comparing staged changes
  git-webdiff --theme monokai    # Start server with custom code theme
"""


def parse(args):
    parser = argparse.ArgumentParser(description='Run webdiff.', usage=USAGE)
    parser.add_argument(
        '--host',
        type=str,
        help='Host name on which to serve git-webdiff UI. Default is localhost.',
        default='localhost',
    )
    parser.add_argument(
        '--port', '-p', type=int, help='Port to run webdiff on.', default=-1
    )
    parser.add_argument(
        '--root-path', type=str, help='Root path for the application (e.g., /webdiff).', default=''
    )
    parser.add_argument(
        '--timeout', type=int, help='Automatically shut down the server after this many minutes. Default: 0 (no timeout). Use 0 to disable.', default=0
    )
    parser.add_argument(
        '--no-timeout', action='store_true', help='Disable automatic timeout (equivalent to --timeout 0).', default=False
    )
    parser.add_argument(
        '--watch', type=int, help='Watch for diff changes and enable reload (poll interval in seconds). Default: 10. Use 0 to disable.', default=10
    )
    parser.add_argument(
        '--no-watch', action='store_true', help='Disable watch mode (equivalent to --watch 0).', default=False
    )

    # Webdiff configuration options
    parser.add_argument(
        '--unified', type=int, help='Number of unified context lines.', default=8
    )
    parser.add_argument(
        '--extra-dir-diff-args', type=str, help='Extra arguments for directory diff.', default=''
    )
    parser.add_argument(
        '--extra-file-diff-args', type=str, help='Extra arguments for file diff.', default=''
    )
    parser.add_argument(
        '--max-diff-width', type=int, help='Maximum width for diff display.', default=160
    )
    parser.add_argument(
        '--theme', type=str, help='Color theme for syntax highlighting.', default='googlecode'
    )
    parser.add_argument(
        '--max-lines-for-syntax', type=int, help='Maximum lines for syntax highlighting.', default=25000
    )

    # Diff algorithm option
    parser.add_argument(
        '--diff-algorithm', type=str, help='Diff algorithm to use.',
        choices=['myers', 'minimal', 'patience', 'histogram'], default=None
    )

    # Color configuration options
    parser.add_argument(
        '--colourblind', '--colorblind',
        action='store_true',
        help='Use colorblind-friendly colors (blue/orange instead of red/green) for deuteranopia accessibility.',
        default=False,
        dest='colourblind'
    )
    parser.add_argument(
        '--color-insert', type=str, help='Background color for inserted lines.', default='#efe'
    )
    parser.add_argument(
        '--color-delete', type=str, help='Background color for deleted lines.', default='#fee'
    )
    parser.add_argument(
        '--color-char-insert', type=str, help='Background color for inserted characters.', default='#cfc'
    )
    parser.add_argument(
        '--color-char-delete', type=str, help='Background color for deleted characters.', default='#fcc'
    )

    # Git integration options
    parser.add_argument(
        '--git-repo',
        type=str,
        action='append',
        dest='git_repos',
        help='Path to git repository with optional label (label:/path/to/repo). Can be specified multiple times for multi-repo support.',
    )
    parser.add_argument(
        '--manage-repos',
        action='store_true',
        help='Enable repository management from the web UI (default for localhost).',
        default=None,
    )
    parser.add_argument(
        '--no-manage-repos',
        action='store_true',
        help='Disable repository management from the web UI.',
        default=False,
    )

    parser.add_argument(
        'git_args',
        type=str,
        nargs='*',
        help='Git arguments to pass to git diff (e.g., HEAD~3..HEAD, --cached, -- file.txt).',
    )
    args = parser.parse_args(args=args)

    # Apply colorblind-friendly colors if flag is set (GitHub's colorblind scheme)
    if args.colourblind:
        # Only override colors that are still at their default values
        # This allows manual color overrides to take precedence
        if args.color_insert == '#efe':
            args.color_insert = '#ddf4ff'  # Light blue (GitHub: diffBlob-additionLine)
        if args.color_delete == '#fee':
            args.color_delete = '#fff1e5'  # Light orange (GitHub: diffBlob-deletionLine)
        if args.color_char_insert == '#cfc':
            args.color_char_insert = '#b6e3ff'  # Medium blue (GitHub: diffBlob-additionWord)
        if args.color_char_delete == '#fcc':
            args.color_char_delete = '#ffd8b5'  # Medium orange (GitHub: diffBlob-deletionWord)

    # Build configuration structure compatible with old git config format
    config = {
        'webdiff': {
            'unified': args.unified,
            'extraDirDiffArgs': args.extra_dir_diff_args,
            'extraFileDiffArgs': args.extra_file_diff_args,
            'port': args.port,
            'host': args.host,
            'rootPath': args.root_path,
            'maxDiffWidth': args.max_diff_width,
            'theme': args.theme,
            'maxLinesForSyntax': args.max_lines_for_syntax,
        },
        'webdiff.colors': {
            'insert': args.color_insert,
            'delete': args.color_delete,
            'charInsert': args.color_char_insert,
            'charDelete': args.color_char_delete,
        },
        'diff': {
            'algorithm': args.diff_algorithm,
        }
    }

    # TODO: convert out to a dataclass
    # Handle --no-watch flag (overrides --watch)
    watch_interval = 0 if args.no_watch else args.watch
    # Handle --no-timeout flag (overrides --timeout)
    timeout_minutes = 0 if args.no_timeout else args.timeout

    # Parse git repos
    if args.git_repos:
        repos = [parse_git_repo_arg(arg) for arg in args.git_repos]
        repos = ensure_unique_labels(repos)
    else:
        # Default: current directory
        cwd = os.getcwd()
        repos = [{'label': os.path.basename(cwd), 'path': cwd}]

    # Validate repo list
    valid, error = validate_repo_list(repos)
    if not valid:
        raise UsageError(f"Invalid repository configuration: {error}")

    # Determine manage_repos setting with security-aware defaults
    is_localhost = args.host in ('localhost', '127.0.0.1')

    if args.no_manage_repos:
        # Explicit --no-manage-repos always disables
        manage_repos_enabled = False
    elif args.manage_repos:
        # Explicit --manage-repos always enables
        manage_repos_enabled = True
    else:
        # Default behavior based on host
        if is_localhost:
            # Default to enabled for localhost
            manage_repos_enabled = True
        else:
            # Default to disabled for non-localhost
            manage_repos_enabled = False
            import sys
            print("WARNING: Repository management is disabled by default when --host is not localhost.", file=sys.stderr)
            print("         Use --manage-repos to explicitly enable it.", file=sys.stderr)

    # Security warning if manage-repos is enabled on non-localhost
    if manage_repos_enabled and not is_localhost:
        import sys
        print("", file=sys.stderr)
        print("⚠️  SECURITY WARNING ⚠️", file=sys.stderr)
        print("Repository management is enabled on a non-localhost host!", file=sys.stderr)
        print(f"Any user connecting to {args.host} will be able to:", file=sys.stderr)
        print("  - Add arbitrary paths from the server's filesystem", file=sys.stderr)
        print("  - Read files from any git repository on the server", file=sys.stderr)
        print("  - See directory structure and file contents", file=sys.stderr)
        print("", file=sys.stderr)
        print("Only enable this if you trust all users with network access to this host.", file=sys.stderr)
        print("", file=sys.stderr)

    out = {
        'config': config,
        'port': args.port,
        'host': args.host,
        'timeout': timeout_minutes,
        'watch': watch_interval,
        'repos': repos,  # List of {label, path} dicts
        'git_args': args.git_args,  # All positional args are git arguments
        'manage_repos': manage_repos_enabled,  # Enable repo management from UI
    }

    return out
