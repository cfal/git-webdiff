#!/usr/bin/env python

import atexit
import dataclasses
import hashlib
import json
import logging
import mimetypes
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import ClientDisconnect
from binaryornot.check import is_binary
import uvicorn

from . import argparser, diff, dirdiff, util

def determine_path():
    """Borrowed from wxglade.py"""
    try:
        root = __file__
        if os.path.islink(root):
            root = os.path.realpath(root)
        return os.path.dirname(os.path.abspath(root))
    except Exception as e:
        print(f"I'm sorry, but something is wrong. Error: {e}")
        print('There is no __file__ variable. Please contact the author.')
        sys.exit()


SERVER_CONFIG = {}
PORT = None
HOSTNAME = 'localhost'
DEBUG = os.environ.get('DEBUG')
WEBDIFF_DIR = determine_path()

# Multi-repo support
REPOS = []  # List of {label, path} dicts
REPO_STATES = []  # List of state dicts (indexed by repo_idx)
                  # Each state: {
                  #   git_args: [],
                  #   difftool_proc: Process,
                  #   diff: [],
                  #   initial_checksum: str,
                  #   current_checksum: str,
                  #   difftool_lock: Lock,
                  #   diff_lock: Lock,
                  #   checksum_lock: Lock,
                  #   reload_in_progress: bool,
                  #   reload_lock: Lock
                  # }
GIT_ARGS = []  # Global default git args (used for all repos initially)
WATCH_ENABLED = False  # Global watch setting
MANAGE_REPOS_ENABLED = False  # Enable repo management from UI

# Timeout support
START_TIME = None  # Server start time
TIMEOUT_MINUTES = 0  # Timeout in minutes (0 = no timeout)
PARSED_ARGS = None  # Stored parsed arguments for reload


def get_repo_idx_by_label(label: str) -> Optional[int]:
    """Get repo index by label.

    Args:
        label: Repo label to search for

    Returns:
        Index of repo, or None if not found
    """
    for idx, repo in enumerate(REPOS):
        if repo['label'] == label:
            return idx
    return None


def init_repo_state(repo: dict, git_args: list) -> dict:
    """Initialize state for a single repo.

    Args:
        repo: Repo dict with 'label' and 'path' keys
        git_args: Initial git arguments

    Returns:
        State dict for this repo
    """
    return {
        'git_args': git_args.copy(),
        'difftool_proc': None,
        'diff': [],
        'initial_checksum': None,
        'current_checksum': None,
        'difftool_lock': threading.Lock(),
        'diff_lock': threading.Lock(),
        'checksum_lock': threading.Lock(),
        'reload_in_progress': False,
        'reload_lock': threading.Lock(),
    }


class ClientDisconnectMiddleware(BaseHTTPMiddleware):
    """Middleware to handle client disconnects gracefully."""
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except ClientDisconnect:
            # Client disconnected, just return a simple response
            return JSONResponse({'error': 'Client disconnected'}, status_code=499)

class CachedStaticFiles(StaticFiles):
    """Static files handler with caching headers."""
    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)

        # Set cache headers based on file type
        if path.endswith(('.js', '.css')):
            # JavaScript and CSS files: no-cache during development
            response.headers['Cache-Control'] = 'no-cache, must-revalidate'
        elif path.endswith(('.jpg', '.jpeg', '.png', '.gif', '.ico', '.svg', '.woff', '.woff2', '.ttf', '.eot')):
            # Images and fonts: cache for 1 month
            response.headers['Cache-Control'] = 'public, max-age=2592000'
        else:
            # Other files: cache for 1 hour
            response.headers['Cache-Control'] = 'public, max-age=3600'

        return response

def create_app(root_path: str = "") -> FastAPI:
    """Create and configure the FastAPI app with the given root_path."""
    app = FastAPI(root_path=root_path)

    # Add middlewares
    app.add_middleware(ClientDisconnectMiddleware)  # Handle client disconnects
    app.add_middleware(GZipMiddleware)  # Compress responses

    # Mount static files
    static_dir = os.path.join(WEBDIFF_DIR, 'static')
    if not os.path.exists(static_dir):
        # Try to find static dir relative to the package
        import webdiff
        webdiff_package_dir = os.path.dirname(webdiff.__file__)
        static_dir = os.path.join(webdiff_package_dir, 'static')

    app.mount("/static", CachedStaticFiles(directory=static_dir), name="static")

    @app.get("/favicon.ico")
    async def handle_favicon():
        favicon_path = os.path.join(WEBDIFF_DIR, 'static/img/favicon.ico')

        # Try alternate path if the primary one doesn't exist
        if not os.path.exists(favicon_path):
            import webdiff
            webdiff_package_dir = os.path.dirname(webdiff.__file__)
            favicon_path = os.path.join(webdiff_package_dir, 'static/img/favicon.ico')

        return FileResponse(
            favicon_path,
            headers={"Cache-Control": "public, max-age=2592000"}  # Cache for 30 days
        )


    @app.get("/theme.css")
    async def handle_theme():
        try:
            if not SERVER_CONFIG:
                return JSONResponse({'error': 'SERVER_CONFIG not initialized'}, status_code=500)
            theme = SERVER_CONFIG.get('webdiff', {}).get('theme', 'googlecode')
            # Handle both 'googlecode' and 'subfolder/themename' formats
            if '/' in theme:
                theme_dir = os.path.dirname(theme)
                theme_file = os.path.basename(theme)
            else:
                theme_dir = ''
                theme_file = theme

            if theme_dir:
                theme_path = os.path.join(
                    WEBDIFF_DIR, 'static/css/themes', theme_dir, theme_file + '.css'
                )
            else:
                theme_path = os.path.join(
                    WEBDIFF_DIR, 'static/css/themes', theme_file + '.css'
                )

            # Try alternate path if the primary one doesn't exist
            if not os.path.exists(theme_path):
                import webdiff
                webdiff_package_dir = os.path.dirname(webdiff.__file__)
                if theme_dir:
                    theme_path = os.path.join(
                        webdiff_package_dir, 'static/css/themes', theme_dir, theme_file + '.css'
                    )
                else:
                    theme_path = os.path.join(
                        webdiff_package_dir, 'static/css/themes', theme_file + '.css'
                    )

            return FileResponse(theme_path)
        except Exception as e:
            logging.error(f"Error in handle_theme: {e}")
            return JSONResponse({'error': str(e)}, status_code=500)


    @app.get("/")
    async def handle_index(request: Request):
        """Main page - uses repo label in query string for cacheability."""
        try:
            # Get repo label from query string, default to first repo
            repo_label = request.query_params.get('repo', REPOS[0]['label'] if REPOS else None)

            if not repo_label:
                return JSONResponse({'error': 'No repositories configured'}, status_code=500)

            # Find repo index by label
            repo_idx = get_repo_idx_by_label(repo_label)

            if repo_idx is None:
                # Invalid label, redirect to first repo
                from fastapi.responses import RedirectResponse
                return RedirectResponse(url=f"/?repo={REPOS[0]['label']}")

            repo = REPOS[repo_idx]
            state = REPO_STATES[repo_idx]

            # Get diff data for this repo
            with state['diff_lock']:
                pairs = diff.get_thin_list(state['diff'])

            # Find template
            index_path = os.path.join(WEBDIFF_DIR, 'templates/file_diff.html')

            if DEBUG:
                logging.info(f"WEBDIFF_DIR: {WEBDIFF_DIR}")
                logging.info(f"Looking for template at: {index_path}")
                logging.info(f"Template exists: {os.path.exists(index_path)}")

            if not os.path.exists(index_path):
                import webdiff
                webdiff_package_dir = os.path.dirname(webdiff.__file__)
                index_path = os.path.join(webdiff_package_dir, 'templates/file_diff.html')

                if DEBUG:
                    logging.info(f"Trying package path: {index_path}")
                    logging.info(f"Template exists at package path: {os.path.exists(index_path)}")

            with open(index_path) as f:
                html = f.read()

                # Inject data for multi-repo
                data = {
                    'repos': REPOS,  # List of {label, path}
                    'current_repo_label': repo_label,
                    'current_repo_idx': repo_idx,  # For API calls
                    'pairs': pairs,
                    'git_args': state['git_args'],
                    'has_magick': util.is_imagemagick_available(),
                    'server_config': SERVER_CONFIG,
                    'root_path': app.root_path,
                    'watch_enabled': WATCH_ENABLED,
                    'manage_repos_enabled': MANAGE_REPOS_ENABLED,
                }

                html = html.replace('{{data}}', json.dumps(data, indent=2))
                html = html.replace('{{ root_path }}', app.root_path)

                # Add JS version for cache busting
                js_path = os.path.join(WEBDIFF_DIR, 'static/js/file_diff.js')
                if not os.path.exists(js_path):
                    import webdiff
                    webdiff_package_dir = os.path.dirname(webdiff.__file__)
                    js_path = os.path.join(webdiff_package_dir, 'static/js/file_diff.js')
                js_version = str(int(os.path.getmtime(js_path))) if os.path.exists(js_path) else '1'
                html = html.replace('{{ js_version }}', js_version)

            return HTMLResponse(content=html)
        except Exception as e:
            logging.error(f"Error handling index: {e}")
            logging.error(f"WEBDIFF_DIR was: {WEBDIFF_DIR}")
            return JSONResponse({'error': str(e)}, status_code=500)




    def check_for_long_lines(content: str, max_length: int = 500):
        """Check if content has lines exceeding max_length.

        Returns (has_long_lines, num_lines_affected, total_bytes_over_limit)
        """
        if not content:
            return False, 0, 0

        lines = content.split('\n')
        lines_affected = 0
        bytes_over = 0

        for line in lines:
            if len(line) > max_length:
                lines_affected += 1
                bytes_over += len(line) - max_length

        return lines_affected > 0, lines_affected, bytes_over

    @app.get("/file/{repo_idx}/{idx}")
    async def get_file_complete(
        repo_idx: int,
        idx: int,
        normalize_json: bool = False,
        options: Optional[str] = None,  # Comma-separated diff options
        no_truncate: int = 0  # Set to 1 to disable truncation
    ):
        """Get all data needed to render a file diff in one request."""
        global SERVER_CONFIG

        # Validate repo index
        if repo_idx < 0 or repo_idx >= len(REPOS):
            return JSONResponse({'error': f'Invalid repo index: {repo_idx}'}, status_code=404)

        state = REPO_STATES[repo_idx]

        # Maximum line length before we warn about truncation
        MAX_LINE_LENGTH = 500

        # Validate file index
        with state['diff_lock']:
            diff_list = state['diff']
            if idx < 0 or idx >= len(diff_list):
                return JSONResponse({'error': f'Invalid file index {idx}'}, status_code=400)
            file_pair = diff_list[idx]

        # Get thick data (metadata)
        thick_data = diff.get_thick_dict(file_pair)

        # Prepare response
        response = {
            'idx': idx,
            'thick': thick_data,
            'truncated': False,
            'truncated_lines': 0,
            'truncated_bytes': 0,
            'content_a': None,
            'content_b': None,
            'diff_ops': []
        }

        # First, check if we need to warn about long lines (unless no_truncate is set)
        if no_truncate == 0:
            # Read files to check for long lines
            content_a_to_check = None
            content_b_to_check = None

            if file_pair.a:
                try:
                    abs_path_a = file_pair.a_path
                    if not is_binary(abs_path_a):
                        path_to_read = util.normalize_json(abs_path_a) if normalize_json else abs_path_a
                        with open(path_to_read, 'r') as f:
                            content_a_to_check = f.read()
                except:
                    pass

            if file_pair.b:
                try:
                    abs_path_b = file_pair.b_path
                    if not is_binary(abs_path_b):
                        path_to_read = util.normalize_json(abs_path_b) if normalize_json else abs_path_b
                        with open(path_to_read, 'r') as f:
                            content_b_to_check = f.read()
                except:
                    pass

            # Check both sides for long lines
            has_long_a, lines_a, bytes_a = check_for_long_lines(content_a_to_check, MAX_LINE_LENGTH)
            has_long_b, lines_b, bytes_b = check_for_long_lines(content_b_to_check, MAX_LINE_LENGTH)

            if has_long_a or has_long_b:
                # Return truncation warning without content
                response['truncated'] = True
                response['truncated_lines'] = lines_a + lines_b
                response['truncated_bytes'] = bytes_a + bytes_b
                return JSONResponse(response)

        # If we get here, either no_truncate=1 or no long lines detected
        # Get content for side A
        if file_pair.a:
            try:
                abs_path_a = file_pair.a_path
                if is_binary(abs_path_a):
                    response['content_a'] = f'Binary file ({os.path.getsize(abs_path_a)} bytes)'
                else:
                    path_to_read = util.normalize_json(abs_path_a) if normalize_json else abs_path_a
                    with open(path_to_read, 'r') as f:
                        response['content_a'] = f.read()
            except Exception as e:
                response['content_a'] = f'Error reading file: {str(e)}'

        # Get content for side B
        if file_pair.b:
            try:
                abs_path_b = file_pair.b_path
                if is_binary(abs_path_b):
                    response['content_b'] = f'Binary file ({os.path.getsize(abs_path_b)} bytes)'
                else:
                    path_to_read = util.normalize_json(abs_path_b) if normalize_json else abs_path_b
                    with open(path_to_read, 'r') as f:
                        response['content_b'] = f.read()
            except Exception as e:
                response['content_b'] = f'Error reading file: {str(e)}'

        # Get diff operations
        try:
            diff_options = options.split(',') if options else []
            extra_args = SERVER_CONFIG['webdiff'].get('extraFileDiffArgs', '')
            if extra_args:
                diff_options += extra_args.split(' ')

            diff_ops = [
                dataclasses.asdict(op)
                for op in diff.get_diff_ops(file_pair, diff_options, normalize_json=normalize_json)
            ]
            response['diff_ops'] = diff_ops
        except Exception as e:
            # Still return file contents even if diff fails
            response['diff_error'] = str(e)

        return JSONResponse(response)

    @app.get("/{side}/image/{repo_idx}/{path:path}")
    async def handle_get_image(side: str, repo_idx: int, path: str):
        if repo_idx < 0 or repo_idx >= len(REPOS):
            return JSONResponse({'error': f'Invalid repo index: {repo_idx}'}, status_code=404)

        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type or not mime_type.startswith('image/'):
            return JSONResponse({'error': 'wrong type'}, status_code=400)

        state = REPO_STATES[repo_idx]

        with state['diff_lock']:
            diff_list = state['diff']
            idx = diff.find_diff_index(diff_list, side, path)

        if idx is None:
            return JSONResponse({'error': 'not found'}, status_code=400)

        d = diff_list[idx]
        abs_path = d.a_path if side == 'a' else d.b_path
        return FileResponse(abs_path, media_type=mime_type)


    @app.get("/pdiff/{repo_idx}/{idx}")
    async def handle_pdiff(repo_idx: int, idx: int):
        if repo_idx < 0 or repo_idx >= len(REPOS):
            return JSONResponse({'error': f'Invalid repo index: {repo_idx}'}, status_code=404)

        state = REPO_STATES[repo_idx]

        with state['diff_lock']:
            if idx < 0 or idx >= len(state['diff']):
                return JSONResponse({'error': f'Invalid file index: {idx}'}, status_code=400)
            d = state['diff'][idx]

        try:
            _, pdiff_image = util.generate_pdiff_image(d.a_path, d.b_path)
            dilated_image_path = util.generate_dilated_pdiff_image(pdiff_image)
            return FileResponse(dilated_image_path)
        except util.ImageMagickNotAvailableError:
            return Response(content='ImageMagick is not available', status_code=501)
        except util.ImageMagickError as e:
            return Response(content=f'ImageMagick error {e}', status_code=501)


    @app.get("/pdiffbbox/{repo_idx}/{idx}")
    async def handle_pdiff_bbox(repo_idx: int, idx: int):
        if repo_idx < 0 or repo_idx >= len(REPOS):
            return JSONResponse({'error': f'Invalid repo index: {repo_idx}'}, status_code=404)

        state = REPO_STATES[repo_idx]

        with state['diff_lock']:
            if idx < 0 or idx >= len(state['diff']):
                return JSONResponse({'error': f'Invalid file index: {idx}'}, status_code=400)
            d = state['diff'][idx]

        try:
            _, pdiff_image = util.generate_pdiff_image(d.a_path, d.b_path)
            bbox = util.get_pdiff_bbox(pdiff_image)
            return JSONResponse(bbox)
        except util.ImageMagickNotAvailableError:
            return JSONResponse('ImageMagick is not available', status_code=501)
        except util.ImageMagickError as e:
            return JSONResponse(f'ImageMagick error {e}', status_code=501)

    @app.get("/api/diff-changed/{repo_idx}")
    async def diff_changed(repo_idx: int):
        """Check if diff has changed for a specific repo."""
        if repo_idx < 0 or repo_idx >= len(REPOS):
            return JSONResponse({'error': f'Invalid repo index: {repo_idx}'}, status_code=404)

        if not WATCH_ENABLED:
            return JSONResponse(
                {
                    'watch_enabled': False,
                    'changed': False
                },
                headers={
                    'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
                    'Pragma': 'no-cache',
                    'Expires': '0'
                }
            )

        state = REPO_STATES[repo_idx]

        # Check if checksum has changed for this repo
        with state['checksum_lock']:
            changed = (state['initial_checksum'] is not None and
                      state['current_checksum'] is not None and
                      state['current_checksum'] != state['initial_checksum'])
            if DEBUG and changed:
                logging.debug(f"Repo {repo_idx} checksums differ: initial={state['initial_checksum'][:8] if state['initial_checksum'] else None}, current={state['current_checksum'][:8] if state['current_checksum'] else None}")

        return JSONResponse(
            {
                'watch_enabled': True,
                'changed': changed
            },
            headers={
                'Cache-Control': 'no-store, no-cache, must-revalidate, max-age=0',
                'Pragma': 'no-cache',
                'Expires': '0'
            }
        )

    @app.get("/api/commits/{repo_idx}")
    async def get_commits(repo_idx: int, limit: int = 50, offset: int = 0):
        """Get commit history for a specific repo.

        Returns a list of commits with hash, message, author, and date.
        """
        if repo_idx < 0 or repo_idx >= len(REPOS):
            return JSONResponse({'error': f'Invalid repo index: {repo_idx}'}, status_code=404)

        repo = REPOS[repo_idx]
        repo_path = repo['path']

        try:
            # Get current branch name
            branch_cmd = ['git', 'rev-parse', '--abbrev-ref', 'HEAD']
            branch_result = subprocess.run(
                branch_cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=5
            )
            branch = branch_result.stdout.strip() if branch_result.returncode == 0 else None

            # Git log format: hash|short_hash|subject|author|date
            # Using %aI for ISO 8601 date format
            cmd = [
                'git', 'log',
                f'--pretty=format:%H|%h|%s|%an|%aI',
                f'-n{limit + 1}',  # Get one extra to check if there are more
                f'--skip={offset}'
            ]

            result = subprocess.run(
                cmd,
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                return JSONResponse({
                    'error': f'git log failed: {result.stderr}'
                }, status_code=500)

            commits = []
            lines = result.stdout.strip().split('\n') if result.stdout.strip() else []

            # Check if there are more commits
            has_more = len(lines) > limit
            lines = lines[:limit]  # Only return requested amount

            for line in lines:
                if not line:
                    continue
                parts = line.split('|', 4)
                if len(parts) >= 5:
                    hash_full, short_hash, message, author, date_iso = parts
                    # Calculate relative time
                    try:
                        from datetime import datetime, timezone
                        commit_date = datetime.fromisoformat(date_iso.replace('Z', '+00:00'))
                        now = datetime.now(timezone.utc)
                        delta = now - commit_date

                        if delta.days > 365:
                            years = delta.days // 365
                            relative = f"{years}y ago"
                        elif delta.days > 30:
                            months = delta.days // 30
                            relative = f"{months}mo ago"
                        elif delta.days > 0:
                            relative = f"{delta.days}d ago"
                        elif delta.seconds > 3600:
                            hours = delta.seconds // 3600
                            relative = f"{hours}h ago"
                        elif delta.seconds > 60:
                            mins = delta.seconds // 60
                            relative = f"{mins}m ago"
                        else:
                            relative = "just now"
                    except:
                        relative = date_iso[:10]  # Fallback to date

                    commits.append({
                        'hash': hash_full,
                        'short_hash': short_hash,
                        'message': message,
                        'author': author,
                        'date': date_iso,
                        'relative': relative
                    })

            return JSONResponse({
                'commits': commits,
                'has_more': has_more,
                'branch': branch
            })

        except subprocess.TimeoutExpired:
            return JSONResponse({'error': 'git log timed out'}, status_code=500)
        except Exception as e:
            logging.error(f"Error getting commits for repo {repo_idx}: {e}")
            return JSONResponse({'error': str(e)}, status_code=500)

    @app.post("/api/server-reload/{repo_idx}")
    async def server_reload(repo_idx: int, request: Request):
        """Reload a specific repo.

        Optional JSON body: {"git_args": ["HEAD~3..HEAD"]} to change diff scope.

        This endpoint blocks until the refresh is complete, then returns success.
        The frontend will reload the page after getting the response.
        """
        if repo_idx < 0 or repo_idx >= len(REPOS):
            return JSONResponse({'error': f'Invalid repo index: {repo_idx}'}, status_code=404)

        try:
            # Parse optional git_args from request body
            new_git_args = None
            try:
                body = await request.json()
                if 'git_args' in body:
                    new_git_args = body['git_args']
            except:
                pass  # No body or invalid JSON, use current args

            # Call refresh_repo_diff synchronously (it returns success, message)
            success, message = refresh_repo_diff(repo_idx, new_git_args)

            if success:
                return JSONResponse({
                    'success': True,
                    'message': message
                })
            else:
                return JSONResponse({
                    'success': False,
                    'error': message
                }, status_code=500)

        except Exception as e:
            logging.error(f"Error in server_reload for repo {repo_idx}: {e}")
            return JSONResponse({
                'success': False,
                'error': str(e)
            }, status_code=500)

    @app.post("/api/repos/validate")
    async def validate_repo_endpoint(request: Request):
        """Validate a single repository."""
        if not MANAGE_REPOS_ENABLED:
            return JSONResponse({
                'valid': False,
                'error': 'Repository management not enabled (use --manage-repos flag)'
            }, status_code=403)

        try:
            data = await request.json()
            label = data.get('label', '')
            path = data.get('path', '')

            # Validate the single repo
            valid, error = argparser.validate_single_repo(label, path)

            if valid:
                return JSONResponse({
                    'valid': True,
                    'label': label,
                    'path': os.path.abspath(path)
                })
            else:
                return JSONResponse({
                    'valid': False,
                    'error': error
                })
        except Exception as e:
            logging.error(f"Error in validate_repo: {e}")
            return JSONResponse({
                'valid': False,
                'error': str(e)
            }, status_code=500)

    @app.post("/api/repos/update")
    async def update_repos_endpoint(request: Request):
        """Replace entire repository list."""
        if not MANAGE_REPOS_ENABLED:
            return JSONResponse({
                'success': False,
                'error': 'Repository management not enabled (use --manage-repos flag)'
            }, status_code=403)

        try:
            data = await request.json()
            new_repos = data.get('repos', [])

            # Call update_repos function
            success, error = update_repos(new_repos)

            if success:
                return JSONResponse({
                    'success': True,
                    'repos': REPOS
                })
            else:
                return JSONResponse({
                    'success': False,
                    'error': error
                }, status_code=400)
        except Exception as e:
            logging.error(f"Error in update_repos: {e}")
            return JSONResponse({
                'success': False,
                'error': str(e)
            }, status_code=500)

    return app


def start_git_difftool(git_args, git_cwd):
    """Start git difftool with wrapper and return (process, left_dir, right_dir).

    Returns None if difftool fails to start or can't read directories.
    """
    import shlex

    # First, check if there are any differences using git diff --quiet
    # Exit codes: 0 = no differences, 1 = has differences, 2+ = error
    check_cmd = ['git', 'diff', '--quiet'] + git_args
    logging.debug(f"Checking for differences: {' '.join(check_cmd)}")

    try:
        check_result = subprocess.run(
            check_cmd,
            cwd=git_cwd,
            capture_output=True,
            timeout=30
        )

        if check_result.returncode == 0:
            # No differences found
            logging.info(f"No differences found in {git_cwd} (git diff --quiet returned 0)")
            return None
        elif check_result.returncode > 1:
            # Error occurred
            stderr_str = check_result.stderr.decode() if isinstance(check_result.stderr, bytes) else check_result.stderr
            logging.error(f"git diff --quiet failed with exit code {check_result.returncode}")
            logging.error(f"  Command: {' '.join(check_cmd)}")
            logging.error(f"  Working directory: {git_cwd}")
            if stderr_str:
                logging.error(f"  stderr: {stderr_str}")
            return None
        # If returncode == 1, there are differences, continue with difftool
        logging.debug(f"Differences found, proceeding with difftool")

    except subprocess.TimeoutExpired:
        logging.error(f"git diff --quiet timed out in {git_cwd}")
        return None
    except Exception as e:
        logging.error(f"Error running git diff --quiet: {e}")
        return None

    # Get path to difftool wrapper script
    wrapper_path = os.path.join(WEBDIFF_DIR, 'difftool-wrapper.sh')

    # Make sure wrapper is executable
    os.chmod(wrapper_path, 0o755)

    # Build git difftool command
    cmd = ['git', 'difftool', '-d', '-x', wrapper_path] + git_args

    logging.info(f"Starting git difftool: {' '.join(cmd)}")

    try:
        # Start the process
        proc = subprocess.Popen(
            cmd,
            cwd=git_cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1  # Line buffered
        )

        # Read the two directory paths from stdout
        left_dir = proc.stdout.readline().strip()
        right_dir = proc.stdout.readline().strip()

        if not left_dir or not right_dir:
            # This should not happen since we pre-checked for diffs
            # If it does, it's a real error
            stderr_output = proc.stderr.read() if proc.stderr else ""
            logging.error(f"Failed to read temp directories from difftool wrapper (unexpected - pre-check passed)")
            logging.error(f"  left_dir: '{left_dir}'")
            logging.error(f"  right_dir: '{right_dir}'")
            logging.error(f"  git difftool command: {' '.join(cmd)}")
            logging.error(f"  working directory: {git_cwd}")
            if stderr_output:
                logging.error(f"  stderr: {stderr_output}")
            proc.kill()
            return None

        logging.info(f"Difftool temp dirs: {left_dir}, {right_dir}")

        # Verify directories exist
        if not os.path.isdir(left_dir) or not os.path.isdir(right_dir):
            logging.error(f"Temp directories don't exist: {left_dir}, {right_dir}")
            proc.kill()
            return None

        return proc, left_dir, right_dir

    except Exception as e:
        logging.error(f"Failed to start git difftool: {e}")
        return None


def refresh_repo_diff(repo_idx: int, new_git_args=None):
    """Refresh diff for a specific repo.

    Runs synchronously when user requests reload.

    Args:
        repo_idx: Index of repo to refresh
        new_git_args: Optional new git arguments (for changing diff scope)

    Returns:
        (success, message) tuple
    """
    if repo_idx < 0 or repo_idx >= len(REPOS):
        return False, f"Invalid repo index: {repo_idx}"

    state = REPO_STATES[repo_idx]
    repo = REPOS[repo_idx]
    repo_path = repo['path']

    logging.info(f"refresh_repo_diff() called for repo {repo_idx} ({repo['label']}), new_git_args={new_git_args}")

    with state['reload_lock']:
        if state['reload_in_progress']:
            logging.info(f"Reload already in progress for repo {repo_idx}, returning")
            return False, "Reload already in progress"
        state['reload_in_progress'] = True

    try:
        # Use new args if provided, otherwise use current args
        git_args = new_git_args if new_git_args is not None else state['git_args']

        logging.info(f"Refreshing repo {repo_idx} ({repo['label']}) with args: {git_args}")

        # Kill old difftool process if it exists
        with state['difftool_lock']:
            if state['difftool_proc']:
                try:
                    state['difftool_proc'].terminate()
                    state['difftool_proc'].wait(timeout=5)
                except subprocess.TimeoutExpired:
                    state['difftool_proc'].kill()
                    state['difftool_proc'].wait()
                except Exception as e:
                    logging.warning(f"Error killing old difftool for repo {repo_idx}: {e}")

        # Start new difftool process
        result = start_git_difftool(git_args, repo_path)

        if result is None:
            # No differences found
            logging.info(f"No differences found for repo {repo_idx} with new git args")

            with state['difftool_lock']:
                state['difftool_proc'] = None

            with state['diff_lock']:
                state['diff'] = []

            # Update git_args if new ones were provided
            if new_git_args is not None:
                state['git_args'] = new_git_args

            # Update checksum and reset baseline
            new_checksum = compute_diff_checksum_for_repo(repo_path, git_args)
            with state['checksum_lock']:
                state['current_checksum'] = new_checksum
                state['initial_checksum'] = new_checksum

            with state['reload_lock']:
                state['reload_in_progress'] = False

            return True, "Reloaded (0 files - no differences)"

        new_proc, left_dir, right_dir = result

        # Compute new diff
        try:
            new_diff = dirdiff.gitdiff(left_dir, right_dir, SERVER_CONFIG['webdiff'])

            # Atomically update state
            with state['difftool_lock']:
                state['difftool_proc'] = new_proc

            with state['diff_lock']:
                state['diff'] = new_diff

            # Update git_args if new ones were provided
            if new_git_args is not None:
                state['git_args'] = new_git_args

            # Update checksum and reset baseline
            new_checksum = compute_diff_checksum_for_repo(repo_path, git_args)
            logging.info(f"Reload complete for repo {repo_idx}, resetting checksum to: {new_checksum[:8] if new_checksum else None}")
            with state['checksum_lock']:
                state['current_checksum'] = new_checksum
                state['initial_checksum'] = new_checksum  # Reset baseline to new checksum

            # Clear reload flag
            with state['reload_lock']:
                state['reload_in_progress'] = False

            logging.info(f"Repo {repo_idx} refreshed successfully ({len(new_diff)} files)")
            return True, f"Reloaded {len(new_diff)} files"

        except Exception as e:
            logging.error(f"Failed to compute new diff for repo {repo_idx}: {e}")
            # Kill the new process since we failed
            try:
                new_proc.kill()
            except:
                pass

            with state['reload_lock']:
                state['reload_in_progress'] = False

            return False, f"Failed to compute diff: {str(e)}"

    except Exception as e:
        logging.error(f"Error in refresh_repo_diff for repo {repo_idx}: {e}")
        with state['reload_lock']:
            state['reload_in_progress'] = False
        return False, str(e)


def timeout_thread():
    """Background thread that checks timeout and shuts down server if needed."""
    global START_TIME, TIMEOUT_MINUTES

    if TIMEOUT_MINUTES <= 0:
        return  # No timeout configured

    logging.info(f"Timeout thread started ({TIMEOUT_MINUTES} minutes)")

    while True:
        time.sleep(60)  # Check every minute

        elapsed_minutes = (time.time() - START_TIME) / 60

        if elapsed_minutes >= TIMEOUT_MINUTES:
            logging.info(f"Timeout reached ({TIMEOUT_MINUTES} minutes). Shutting down...")
            os._exit(0)  # Force exit the entire process


def cleanup_difftool_processes():
    """Clean up all difftool processes on shutdown."""
    logging.info("Cleaning up difftool processes...")
    for idx, state in enumerate(REPO_STATES):
        try:
            with state['difftool_lock']:
                if state['difftool_proc']:
                    try:
                        logging.info(f"Terminating difftool process for repo {idx}")
                        state['difftool_proc'].terminate()
                        state['difftool_proc'].wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        logging.warning(f"Difftool process for repo {idx} didn't terminate, killing it")
                        state['difftool_proc'].kill()
                        state['difftool_proc'].wait()
                    except Exception as e:
                        logging.warning(f"Error terminating difftool for repo {idx}: {e}")
        except Exception as e:
            logging.warning(f"Error accessing difftool_lock for repo {idx}: {e}")


def signal_handler(signum, frame):
    """Handle shutdown signals by cleaning up and exiting."""
    logging.info(f"Received signal {signum}, shutting down...")
    cleanup_difftool_processes()
    sys.exit(0)


def random_port():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(('', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def find_port(webdiff_config):
    if webdiff_config['port'] != -1:
        return webdiff_config['port']
    return random_port()


def compute_diff_checksum_for_repo(repo_path: str, git_args: list):
    """Compute checksum of a specific repo's git diff output.

    Args:
        repo_path: Path to the git repository
        git_args: Git arguments to pass to git diff

    Returns:
        SHA256 checksum hex string, or None on error
    """
    try:
        # Re-run the git diff command for this repo
        cmd = ['git', 'diff']
        if git_args:
            cmd += git_args
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            timeout=30  # Prevent hanging
        )

        if result.returncode not in (0, 1):  # 0 = no diff, 1 = has diff
            logging.warning(f"git diff command failed for {repo_path} with code {result.returncode}")
            logging.warning(f"Command was: {' '.join(cmd)}")
            if result.stderr:
                stderr_str = result.stderr.decode() if isinstance(result.stderr, bytes) else result.stderr
                logging.warning(f"git diff stderr: {stderr_str}")
            return None

        # Compute SHA256 checksum of the diff output
        checksum = hashlib.sha256(result.stdout).hexdigest()
        return checksum
    except subprocess.TimeoutExpired:
        logging.error(f"git diff command timed out for {repo_path}")
        return None
    except Exception as e:
        logging.error(f"Error computing diff checksum for {repo_path}: {e}")
        return None


def check_for_changes_thread(poll_interval=5):
    """Background thread that polls for diff changes in all repos.

    Does NOT trigger restarts - just updates the checksums.
    The /api/server-reload endpoint triggers the actual restart.

    Args:
        poll_interval: How often to check (in seconds)
    """
    logging.info(f"Watch thread started for {len(REPOS)} repos (polling every {poll_interval}s)")

    while WATCH_ENABLED:
        for repo_idx, repo in enumerate(REPOS):
            state = REPO_STATES[repo_idx]

            try:
                new_checksum = compute_diff_checksum_for_repo(repo['path'], state['git_args'])

                if new_checksum is None:
                    # Can't compute checksum, skip this repo
                    continue

                with state['checksum_lock']:
                    if new_checksum != state['current_checksum']:
                        logging.info(f"Diff change detected in repo {repo_idx} ({repo['label']}) - old: {state['current_checksum'][:8] if state['current_checksum'] else None}, new: {new_checksum[:8]}")
                    # Always update to latest checksum
                    state['current_checksum'] = new_checksum

            except Exception as e:
                logging.error(f"Error checking repo {repo_idx} ({repo['label']}): {e}")

        time.sleep(poll_interval)


def start_repo(repo_idx: int, repo_path: str, git_args: list, watch_enabled: bool):
    """Start difftool for a repo and populate its state.

    Args:
        repo_idx: Index of repo in REPO_STATES
        repo_path: Path to git repository
        git_args: Initial git arguments
        watch_enabled: Whether watch mode is enabled
    """
    state = REPO_STATES[repo_idx]
    repo_label = REPOS[repo_idx]['label']

    result = start_git_difftool(git_args, repo_path)

    if result is None:
        # No differences
        logging.info(f"Repo {repo_idx} ({repo_label}): No differences found, starting with empty diff")
        state['difftool_proc'] = None
        state['diff'] = []
    else:
        proc, left_dir, right_dir = result
        state['difftool_proc'] = proc
        state['diff'] = dirdiff.gitdiff(left_dir, right_dir, SERVER_CONFIG['webdiff'])
        logging.info(f"Repo {repo_idx} ({repo_label}): Loaded {len(state['diff'])} files")

    # Compute checksums for watch mode
    if watch_enabled:
        checksum = compute_diff_checksum_for_repo(repo_path, git_args)
        state['initial_checksum'] = checksum
        state['current_checksum'] = checksum
        if checksum:
            logging.info(f"Repo {repo_idx} ({repo_label}): Initial checksum: {checksum[:8]}")


def update_repos(new_repos: list) -> tuple:
    """Replace all repos with new list atomically.

    Args:
        new_repos: List of {"label": str, "path": str} dicts

    Returns:
        (success, error_message)
    """
    global REPOS, REPO_STATES

    # Validate all repos first
    valid, error = argparser.validate_repo_list(new_repos)
    if not valid:
        return False, error

    # Save old state for rollback
    old_repos = REPOS.copy()
    old_states = REPO_STATES.copy()

    try:
        # Cleanup old difftool processes
        logging.info("Cleaning up old difftool processes...")
        cleanup_difftool_processes()

        # Replace repos
        REPOS = new_repos.copy()
        REPO_STATES = []

        # Initialize new repos
        logging.info(f"Initializing {len(REPOS)} repos...")
        for idx, repo in enumerate(REPOS):
            state = init_repo_state(repo, GIT_ARGS)
            REPO_STATES.append(state)
            start_repo(idx, repo['path'], GIT_ARGS, WATCH_ENABLED)

        logging.info(f"Successfully updated to {len(REPOS)} repos")
        return True, None

    except Exception as e:
        # Rollback on error
        logging.error(f"Error updating repos, rolling back: {e}")

        try:
            REPOS = old_repos
            REPO_STATES = old_states

            # Restart old repos
            for idx, repo in enumerate(REPOS):
                start_repo(idx, repo['path'], GIT_ARGS, WATCH_ENABLED)
        except Exception as rollback_error:
            logging.error(f"CRITICAL: Rollback failed: {rollback_error}")

        return False, f"Failed to update repos: {str(e)}"


def run():
    global PORT, HOSTNAME, SERVER_CONFIG, PARSED_ARGS
    global REPOS, REPO_STATES, GIT_ARGS, WATCH_ENABLED, START_TIME, TIMEOUT_MINUTES, MANAGE_REPOS_ENABLED

    try:
        parsed_args = argparser.parse(sys.argv[1:])
    except argparser.UsageError as e:
        sys.stderr.write('Error: %s\n\n' % e)
        sys.stderr.write(argparser.USAGE)
        sys.exit(1)

    SERVER_CONFIG = parsed_args['config']
    WEBDIFF_CONFIG = SERVER_CONFIG['webdiff']
    HOSTNAME = parsed_args.get('host', 'localhost')
    PORT = find_port(WEBDIFF_CONFIG)

    if parsed_args.get('port') and parsed_args['port'] != -1:
        PORT = parsed_args['port']

    # Store parsed args for reload functionality
    PARSED_ARGS = parsed_args

    # Extract repos and git args
    REPOS = parsed_args.get('repos', [])
    GIT_ARGS = parsed_args.get('git_args', [])
    MANAGE_REPOS_ENABLED = parsed_args.get('manage_repos', False)

    # Check if watch mode is enabled
    watch_interval = parsed_args.get('watch', 0)
    WATCH_ENABLED = watch_interval > 0

    if WATCH_ENABLED:
        logging.info(f"Watch mode enabled (interval: {watch_interval}s)")

    # Initialize all repos
    REPO_STATES = []
    for idx, repo in enumerate(REPOS):
        state = init_repo_state(repo, GIT_ARGS)
        REPO_STATES.append(state)
        start_repo(idx, repo['path'], GIT_ARGS, WATCH_ENABLED)

    logging.info(f"Initialized {len(REPOS)} repo(s)")

    # Register cleanup handlers
    atexit.register(cleanup_difftool_processes)
    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGINT, signal_handler)

    # Get root_path from config
    root_path = WEBDIFF_CONFIG.get('rootPath', '')

    # Create app with root_path
    app = create_app(root_path)

    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.DEBUG)

    if root_path:
        print(f"Starting git-webdiff server at http://{HOSTNAME}:{PORT}{root_path}")
    else:
        print(f"Starting git-webdiff server at http://{HOSTNAME}:{PORT}")

    # Get timeout value from parsed args and initialize START_TIME
    TIMEOUT_MINUTES = parsed_args.get('timeout', 0)
    START_TIME = time.time()

    # Create server configuration
    config = uvicorn.Config(
        app,
        host=HOSTNAME,
        port=PORT,
        log_level="info" if DEBUG else "error",
        # Performance optimizations
        limit_concurrency=1000,  # Allow more concurrent connections
        timeout_keep_alive=75,   # Keep connections alive longer
    )
    server = uvicorn.Server(config)

    # Start timeout thread if enabled
    if TIMEOUT_MINUTES > 0:
        print(f"Server will automatically shut down after {TIMEOUT_MINUTES} minutes")
        timeout_th = threading.Thread(target=timeout_thread, daemon=True)
        timeout_th.start()

    # Start watch thread if enabled
    if WATCH_ENABLED and watch_interval > 0:
        watch_thread = threading.Thread(
            target=check_for_changes_thread,
            args=(watch_interval,),
            daemon=True
        )
        watch_thread.start()
        print(f"Watch mode active: checking for changes every {watch_interval} seconds")

    # Run server (cleanup happens via signal handlers and atexit)
    server.run()


if __name__ == "__main__":
    run()
