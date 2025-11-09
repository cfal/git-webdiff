#!/usr/bin/env python

import dataclasses
import hashlib
import json
import logging
import mimetypes
import os
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
DIFF = None
PORT = None
HOSTNAME = 'localhost'
DEBUG = os.environ.get('DEBUG')
WEBDIFF_DIR = determine_path()

# Hot reload support (no-restart approach with difftool management)
GIT_ARGS = []  # Original git arguments for git difftool
GIT_CWD = None  # Working directory for git commands
WATCH_ENABLED = False  # Whether watch mode is enabled
INITIAL_CHECKSUM = None  # Checksum when server started
CURRENT_CHECKSUM = None  # Current diff checksum (updated by watch thread)
CHECKSUM_LOCK = threading.Lock()  # Lock for checksum updates

# Difftool process management
DIFFTOOL_PROC = None  # The git difftool process
DIFFTOOL_LOCK = threading.Lock()  # Lock for difftool operations
DIFF_LOCK = threading.Lock()  # Lock for DIFF updates
RELOAD_IN_PROGRESS = False  # Flag to prevent concurrent reloads
RELOAD_LOCK = threading.Lock()  # Lock for reload state

# Timeout support
START_TIME = None  # Server start time
TIMEOUT_MINUTES = 0  # Timeout in minutes (0 = no timeout)
PARSED_ARGS = None  # Stored parsed arguments for reload

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
            # JavaScript and CSS files: cache for 1 week
            response.headers['Cache-Control'] = 'public, max-age=604800'
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
    @app.get("/{idx}")
    async def handle_index(request: Request, idx: Optional[int] = None):
        global DIFF
        try:
            index_path = os.path.join(WEBDIFF_DIR, 'templates/file_diff.html')

            # Debug logging
            if DEBUG:
                logging.info(f"WEBDIFF_DIR: {WEBDIFF_DIR}")
                logging.info(f"Looking for template at: {index_path}")
                logging.info(f"Template exists: {os.path.exists(index_path)}")

            # Try alternate paths if the primary one doesn't exist
            if not os.path.exists(index_path):
                # Try to find the template relative to the package
                import webdiff
                webdiff_package_dir = os.path.dirname(webdiff.__file__)
                index_path = os.path.join(webdiff_package_dir, 'templates/file_diff.html')

                if DEBUG:
                    logging.info(f"Trying package path: {index_path}")
                    logging.info(f"Template exists at package path: {os.path.exists(index_path)}")

            with open(index_path) as f:
                html = f.read()

                # Inject the root path into the data
                data = {
                    'idx': idx if idx is not None else 0,
                    'has_magick': util.is_imagemagick_available(),
                    'pairs': diff.get_thin_list(DIFF),
                    'server_config': SERVER_CONFIG,
                    'root_path': app.root_path,
                    'git_args': GIT_ARGS,  # For the command bar UI
                    'watch_enabled': WATCH_ENABLED,  # Whether hot reload is enabled
                }

                html = html.replace(
                    '{{data}}',
                    json.dumps(data, indent=2)
                )
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

    @app.get("/file/{idx}")
    async def get_file_complete(
        idx: int,
        normalize_json: bool = False,
        options: Optional[str] = None,  # Comma-separated diff options
        no_truncate: int = 0  # Set to 1 to disable truncation
    ):
        """Get all data needed to render a file diff in one request."""
        global DIFF, SERVER_CONFIG

        # Maximum line length before we warn about truncation
        MAX_LINE_LENGTH = 500

        # Validate index
        if idx < 0 or idx >= len(DIFF):
            return JSONResponse({'error': f'Invalid index {idx}'}, status_code=400)

        file_pair = DIFF[idx]

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

    @app.get("/{side}/image/{path:path}")
    async def handle_get_image(side: str, path: str):
        global DIFF
        mime_type, _ = mimetypes.guess_type(path)
        if not mime_type or not mime_type.startswith('image/'):
            return JSONResponse({'error': 'wrong type'}, status_code=400)

        idx = diff.find_diff_index(DIFF, side, path)
        if idx is None:
            return JSONResponse({'error': 'not found'}, status_code=400)

        d = DIFF[idx]
        abs_path = d.a_path if side == 'a' else d.b_path
        return FileResponse(abs_path, media_type=mime_type)


    @app.get("/pdiff/{idx}")
    async def handle_pdiff(idx: int):
        global DIFF
        d = DIFF[idx]
        try:
            _, pdiff_image = util.generate_pdiff_image(d.a_path, d.b_path)
            dilated_image_path = util.generate_dilated_pdiff_image(pdiff_image)
            return FileResponse(dilated_image_path)
        except util.ImageMagickNotAvailableError:
            return Response(content='ImageMagick is not available', status_code=501)
        except util.ImageMagickError as e:
            return Response(content=f'ImageMagick error {e}', status_code=501)


    @app.get("/pdiffbbox/{idx}")
    async def handle_pdiff_bbox(idx: int):
        global DIFF
        d = DIFF[idx]
        try:
            _, pdiff_image = util.generate_pdiff_image(d.a_path, d.b_path)
            bbox = util.get_pdiff_bbox(pdiff_image)
            return JSONResponse(bbox)
        except util.ImageMagickNotAvailableError:
            return JSONResponse('ImageMagick is not available', status_code=501)
        except util.ImageMagickError as e:
            return JSONResponse(f'ImageMagick error {e}', status_code=501)

    @app.get("/api/diff-changed")
    async def diff_changed():
        """Check if diff has changed."""
        global WATCH_ENABLED, INITIAL_CHECKSUM, CURRENT_CHECKSUM

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

        # Check if checksum has changed
        with CHECKSUM_LOCK:
            changed = (INITIAL_CHECKSUM is not None and
                      CURRENT_CHECKSUM is not None and
                      CURRENT_CHECKSUM != INITIAL_CHECKSUM)
            if DEBUG and changed:
                logging.debug(f"Checksums differ: initial={INITIAL_CHECKSUM[:8] if INITIAL_CHECKSUM else None}, current={CURRENT_CHECKSUM[:8] if CURRENT_CHECKSUM else None}")

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

    @app.post("/api/server-reload")
    async def server_reload(request: Request):
        """Trigger diff refresh synchronously.

        Optional JSON body: {"git_args": ["HEAD~3..HEAD"]} to change diff scope.

        This endpoint blocks until the refresh is complete, then returns success.
        The frontend will reload the page after getting the response.
        """
        try:
            # Parse optional git_args from request body
            new_git_args = None
            try:
                body = await request.json()
                if 'git_args' in body:
                    new_git_args = body['git_args']
            except:
                pass  # No body or invalid JSON, use current args

            # Call refresh_diff synchronously (it returns success, message)
            success, message = refresh_diff(new_git_args)

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
            logging.error(f"Error in server_reload: {e}")
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
            logging.error("Failed to read temp directories from difftool wrapper")
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


def refresh_diff(new_git_args=None):
    """Refresh the DIFF by restarting git difftool.

    Runs synchronously when user requests reload.

    Args:
        new_git_args: Optional new git arguments (for changing diff scope)

    Returns:
        (success, message) tuple
    """
    global DIFFTOOL_PROC, DIFF, GIT_ARGS, RELOAD_IN_PROGRESS, CURRENT_CHECKSUM, INITIAL_CHECKSUM

    print(f"refresh_diff() called, new_git_args={new_git_args}")

    with RELOAD_LOCK:
        if RELOAD_IN_PROGRESS:
            print("Reload already in progress, returning")
            return False, "Reload already in progress"
        RELOAD_IN_PROGRESS = True

    try:
        # Use new args if provided, otherwise use current args
        git_args = new_git_args if new_git_args is not None else GIT_ARGS

        logging.info(f"Refreshing diff with args: {git_args}")

        # Kill old difftool process if it exists
        with DIFFTOOL_LOCK:
            if DIFFTOOL_PROC:
                try:
                    DIFFTOOL_PROC.terminate()
                    DIFFTOOL_PROC.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    DIFFTOOL_PROC.kill()
                    DIFFTOOL_PROC.wait()
                except Exception as e:
                    logging.warning(f"Error killing old difftool: {e}")

        # Start new difftool process
        result = start_git_difftool(git_args, GIT_CWD)

        if result is None:
            # No differences found - update to empty diff
            logging.info("No differences found with new git args")

            # Update globals
            with DIFFTOOL_LOCK:
                DIFFTOOL_PROC = None

            with DIFF_LOCK:
                DIFF = []

            # Update GIT_ARGS if new ones were provided
            if new_git_args is not None:
                GIT_ARGS = new_git_args

            # Update checksum and reset baseline
            new_checksum = compute_diff_checksum()
            with CHECKSUM_LOCK:
                CURRENT_CHECKSUM = new_checksum
                INITIAL_CHECKSUM = new_checksum

            with RELOAD_LOCK:
                RELOAD_IN_PROGRESS = False

            return True, "Reloaded (0 files - no differences)"

        new_proc, left_dir, right_dir = result

        # Update global DIFF using dirdiff.gitdiff
        try:
            new_diff = dirdiff.gitdiff(left_dir, right_dir, SERVER_CONFIG['webdiff'])

            # Atomically update globals
            with DIFFTOOL_LOCK:
                DIFFTOOL_PROC = new_proc

            with DIFF_LOCK:
                DIFF = new_diff

            # Update GIT_ARGS if new ones were provided
            if new_git_args is not None:
                GIT_ARGS = new_git_args

            # Update checksum and reset baseline
            new_checksum = compute_diff_checksum()
            print(f"Reload complete, resetting checksum to: {new_checksum[:8] if new_checksum else None}")
            logging.info(f"Reload complete, resetting checksum to: {new_checksum[:8] if new_checksum else None}")
            with CHECKSUM_LOCK:
                old_initial = INITIAL_CHECKSUM
                CURRENT_CHECKSUM = new_checksum
                INITIAL_CHECKSUM = new_checksum  # Reset baseline to new checksum
                print(f"Checksum reset: INITIAL {old_initial[:8] if old_initial else None} -> {INITIAL_CHECKSUM[:8] if INITIAL_CHECKSUM else None}")

            # Clear reload flag
            with RELOAD_LOCK:
                RELOAD_IN_PROGRESS = False

            logging.info(f"Diff refreshed successfully ({len(new_diff)} files)")
            return True, f"Reloaded {len(new_diff)} files"

        except Exception as e:
            logging.error(f"Failed to compute new diff: {e}")
            # Kill the new process since we failed
            try:
                new_proc.kill()
            except:
                pass

            with RELOAD_LOCK:
                RELOAD_IN_PROGRESS = False

            return False, f"Failed to compute diff: {str(e)}"

    except Exception as e:
        logging.error(f"Error in refresh_diff: {e}")
        with RELOAD_LOCK:
            RELOAD_IN_PROGRESS = False
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


def compute_diff_checksum():
    """Compute checksum of the current git diff output.

    Returns None if we don't have git context (can't reload).
    """
    global GIT_ARGS, GIT_CWD

    if not GIT_CWD:
        return None

    try:
        # Re-run the original git diff command
        # If GIT_ARGS is empty, just run 'git diff' (compares working tree to HEAD)
        cmd = ['git', 'diff']
        if GIT_ARGS:
            cmd += GIT_ARGS
        result = subprocess.run(
            cmd,
            cwd=GIT_CWD,
            capture_output=True,
            timeout=30  # Prevent hanging
        )

        if result.returncode not in (0, 1):  # 0 = no diff, 1 = has diff
            logging.warning(f"git diff command failed with code {result.returncode}")
            logging.warning(f"Command was: {' '.join(cmd)}")
            logging.warning(f"Working directory: {GIT_CWD}")
            if result.stderr:
                stderr_str = result.stderr.decode() if isinstance(result.stderr, bytes) else result.stderr
                logging.warning(f"git diff stderr: {stderr_str}")
            return None

        # Compute SHA256 checksum of the diff output
        checksum = hashlib.sha256(result.stdout).hexdigest()
        return checksum
    except subprocess.TimeoutExpired:
        logging.error("git diff command timed out")
        return None
    except Exception as e:
        logging.error(f"Error computing diff checksum: {e}")
        return None


def check_for_changes_thread(poll_interval=5):
    """Background thread that polls for diff changes and updates CURRENT_CHECKSUM.

    Does NOT trigger restarts - just updates the checksum.
    The /api/server-reload endpoint triggers the actual restart.

    Args:
        poll_interval: How often to check (in seconds)
    """
    global CURRENT_CHECKSUM, WATCH_ENABLED

    print(f"Watch thread started (polling every {poll_interval}s)")
    logging.info(f"Watch thread started (polling every {poll_interval}s)")

    while WATCH_ENABLED:
        try:
            new_checksum = compute_diff_checksum()

            if new_checksum is None:
                # Can't compute checksum, sleep and retry
                print(f"Watch thread: checksum is None, skipping")
                time.sleep(poll_interval)
                continue

            with CHECKSUM_LOCK:
                if new_checksum != CURRENT_CHECKSUM:
                    print(f"Diff change detected - old: {CURRENT_CHECKSUM[:8] if CURRENT_CHECKSUM else None}, new: {new_checksum[:8] if new_checksum else None}")
                    logging.info(f"Diff change detected - old: {CURRENT_CHECKSUM[:8] if CURRENT_CHECKSUM else None}, new: {new_checksum[:8] if new_checksum else None}")
                # Always update to latest checksum
                CURRENT_CHECKSUM = new_checksum

            time.sleep(poll_interval)
        except Exception as e:
            print(f"Error in watch thread: {e}")
            logging.error(f"Error in watch thread: {e}")
            time.sleep(poll_interval)


def run():
    global DIFF, PORT, HOSTNAME, SERVER_CONFIG, PARSED_ARGS
    global GIT_ARGS, GIT_CWD, WATCH_ENABLED, INITIAL_CHECKSUM, CURRENT_CHECKSUM
    global DIFFTOOL_PROC, START_TIME, TIMEOUT_MINUTES

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

    # Extract git context from parsed arguments
    GIT_ARGS = parsed_args.get('git_args', [])
    GIT_CWD = parsed_args.get('git_repo', os.getcwd())

    # Check if watch mode is enabled
    watch_interval = parsed_args.get('watch', 0)
    if watch_interval > 0 and GIT_CWD:
        WATCH_ENABLED = True
        # Compute initial checksum
        checksum = compute_diff_checksum()
        INITIAL_CHECKSUM = checksum
        CURRENT_CHECKSUM = checksum
        if CURRENT_CHECKSUM:
            print(f"Watch mode enabled (interval: {watch_interval}s, initial checksum: {CURRENT_CHECKSUM[:8]})")
            logging.info(f"Watch mode enabled (interval: {watch_interval}s)")
        else:
            logging.warning("Watch mode enabled but could not compute initial checksum")
    elif watch_interval > 0:
        logging.warning("Watch mode requested but no git context available (GIT_CWD missing)")

    # Git-only mode: start difftool process and get temp dirs
    if GIT_CWD:
        # We have git context - start difftool process
        result = start_git_difftool(GIT_ARGS, GIT_CWD)
        if result is None:
            # No differences found - start with empty diff
            # User can change git args from UI to see different diffs
            logging.info("No differences found with initial git args, starting with empty diff")
            DIFF = []
            DIFFTOOL_PROC = None
        else:
            DIFFTOOL_PROC, left_dir, right_dir = result
            DIFF = dirdiff.gitdiff(left_dir, right_dir, WEBDIFF_CONFIG)
    else:
        # No git context provided
        DIFF = []

    # Get root_path from config
    root_path = WEBDIFF_CONFIG.get('rootPath', '')

    # Create app with root_path
    app = create_app(root_path)

    logging.basicConfig(format='%(asctime)s %(levelname)-8s %(message)s', level=logging.DEBUG)

    if root_path:
        print(f"Starting webdiff server at http://{HOSTNAME}:{PORT}{root_path}")
    else:
        print(f"Starting webdiff server at http://{HOSTNAME}:{PORT}")

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

    # Run server with graceful shutdown handling
    try:
        server.run()
    except KeyboardInterrupt:
        # Clean up difftool process if it exists
        with DIFFTOOL_LOCK:
            if DIFFTOOL_PROC:
                try:
                    DIFFTOOL_PROC.terminate()
                    DIFFTOOL_PROC.wait(timeout=5)
                except:
                    pass
        sys.exit(0)


if __name__ == "__main__":
    run()
