"""Parse command line arguments to webdiff."""

import argparse
import os


class UsageError(Exception):
    pass


USAGE = """Usage: git-webdiff [options] [git_args ...]

Web-based git difftool for viewing diffs in your browser.

Examples:
  git-webdiff                    # Compare working directory with HEAD
  git-webdiff HEAD~3..HEAD       # Compare specific commits
  git-webdiff --cached           # Compare staged changes
  git-webdiff --theme monokai    # Use custom theme
"""


def parse(args):
    parser = argparse.ArgumentParser(description='Run webdiff.', usage=USAGE)
    parser.add_argument(
        '--host',
        type=str,
        help='Host name on which to serve webdiff UI. Default is localhost.',
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
        '--git-repo', type=str, help='Path to git repository. Defaults to current directory.', default=None
    )

    parser.add_argument(
        'git_args',
        type=str,
        nargs='*',
        help='Git arguments to pass to git diff (e.g., HEAD~3..HEAD, --cached, -- file.txt).',
    )
    args = parser.parse_args(args=args)

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

    out = {
        'config': config,
        'port': args.port,
        'host': args.host,
        'timeout': timeout_minutes,
        'watch': watch_interval,
        'git_repo': args.git_repo if args.git_repo else os.getcwd(),
        'git_args': args.git_args,  # All positional args are git arguments
    }

    return out
