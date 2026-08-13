"""
api/stats.py
------------
Vercel serverless function — public GitHub Stats Card API.

Endpoint:
  GET /api/stats?username=<github-login>

Returns:
  - 200 + SVG body (Content-Type: image/svg+xml) on success
  - 200 + error SVG body for user-visible errors (not-found, invalid input)
  - 400 + error SVG for missing / malformed username
  - 500 + error SVG for unexpected server errors

Cache headers:
  Cache-Control: public, s-maxage=3600, stale-while-revalidate=86400

  The Vercel CDN will serve a cached copy for up to 1 hour per username.
  A CDN cache miss may trigger multiple GitHub GraphQL calls depending on
  how many years of contribution history the user has.

Security:
  - GITHUB_TOKEN is read from the server-side environment only.
  - The token is NEVER sent in responses, logs, or headers.
  - Username is validated against GitHub's login format before any API call.
  - Stack traces and internal paths are NEVER exposed to callers.

Usage (embed in README):
  ![GitHub Stats](https://your-domain/api/stats?username=YOUR_USERNAME)
"""

import os
import re
import sys
from http.server import BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs


# ---------------------------------------------------------------------------
# Constants  (defined at module level — safe, no imports from lib needed)
# ---------------------------------------------------------------------------

# GitHub's documented login format: alphanumeric + hyphens, 1–39 chars,
# cannot start or end with a hyphen.
_USERNAME_RE = re.compile(
    r'^[a-zA-Z0-9][a-zA-Z0-9-]{0,37}[a-zA-Z0-9]$|^[a-zA-Z0-9]$'
)

_SVG_CONTENT_TYPE = "image/svg+xml; charset=utf-8"
_CACHE_CONTROL    = "public, s-maxage=3600, stale-while-revalidate=86400"


# ---------------------------------------------------------------------------
# Helpers  (pure stdlib — no lib imports needed)
# ---------------------------------------------------------------------------

def _get_token():
    """
    Read GITHUB_TOKEN from the server-side environment.
    Raises RuntimeError if absent. Token is NEVER included in any response.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is not configured in the deployment environment."
        )
    return token


def _validate_username(username):
    """
    Validate a username against GitHub's login format.

    Returns (True, "") on success.
    Returns (False, reason) on failure — reason is user-visible and safe.
    """
    if not username:
        return False, "username is required"
    if len(username) > 39:
        return False, "username too long (max 39 characters)"
    if not _USERNAME_RE.match(username):
        return False, "invalid username format"
    return True, ""


def _send_svg(req_handler, svg_body, status=200, extra_headers=None):
    """Write an SVG HTTP response through the BaseHTTPRequestHandler."""
    body = svg_body.encode("utf-8")
    req_handler.send_response(status)
    req_handler.send_header("Content-Type", _SVG_CONTENT_TYPE)
    req_handler.send_header("Content-Length", str(len(body)))
    req_handler.send_header("Cache-Control", _CACHE_CONTROL)
    req_handler.send_header("X-Content-Type-Options", "nosniff")
    if extra_headers:
        for key, value in extra_headers.items():
            req_handler.send_header(key, value)
    req_handler.end_headers()
    req_handler.wfile.write(body)


def _ensure_lib_path():
    """
    Add the repository root to sys.path so that `lib.stats_engine` and
    `lib.svg_renderer` are importable.

    Called lazily inside do_GET() so that the `class handler` definition at
    module level is always visible to Vercel's build scanner even before any
    imports from lib/ are attempted.
    """
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)


# ---------------------------------------------------------------------------
# Vercel serverless handler
#
# IMPORTANT: `class handler` must be defined at the module top level with no
# import errors above it.  Vercel scans api/stats.py for a top-level
# `handler` class that inherits from BaseHTTPRequestHandler.  If any
# top-level import raises an ImportError the scanner reports:
#   "No python entrypoint found … api/stats.py (variable: handler)"
#
# For this reason, all imports from lib/ are done lazily inside do_GET()
# rather than at the top of the file.
# ---------------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):
    """
    Vercel Python serverless function handler.

    Vercel auto-discovers this class in api/stats.py and routes
    GET /api/stats to do_GET().
    """

    def do_GET(self):
        # ── Lazy import of lib/ modules ──────────────────────────────────────
        # Done here (not at module top level) so that Vercel's build scanner
        # can always see `class handler` above without tripping on an
        # ImportError when lib/ is not yet on sys.path.
        _ensure_lib_path()
        from lib.stats_engine import build_stats          # noqa: PLC0415
        from lib.svg_renderer import build_timeline_svg, build_error_svg  # noqa: PLC0415

        # ── Parse query string ───────────────────────────────────────────────
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        username = params.get("username", [""])[0].strip()

        # ── Validate username ────────────────────────────────────────────────
        valid, reason = _validate_username(username)
        if not valid:
            error_svg = build_error_svg(
                "Invalid Request",
                f"?username={reason}"
            )
            _send_svg(self, error_svg, status=400,
                      extra_headers={"Cache-Control": "no-store"})
            return

        # ── Read server-side token ───────────────────────────────────────────
        try:
            token = _get_token()
        except RuntimeError:
            error_svg = build_error_svg(
                "Service configuration error",
                "Please try again later."
            )
            _send_svg(self, error_svg, status=500,
                      extra_headers={"Cache-Control": "no-store"})
            return

        # ── Fetch stats from GitHub ──────────────────────────────────────────
        try:
            stats = build_stats(username, token)
        except ValueError:
            error_svg = build_error_svg(
                f"GitHub user not found: {username}",
                "Check the spelling and try again."
            )
            _send_svg(self, error_svg, status=200,
                      extra_headers={"Cache-Control": "no-store"})
            return
        except RuntimeError as exc:
            msg = str(exc)
            safe_msg = msg if "token" not in msg.lower() else "GitHub API error"
            error_svg = build_error_svg(
                "GitHub API error",
                safe_msg[:80]
            )
            _send_svg(self, error_svg, status=200,
                      extra_headers={"Cache-Control": "no-store"})
            return
        except Exception:
            error_svg = build_error_svg(
                "Unexpected error",
                "Please try again later."
            )
            _send_svg(self, error_svg, status=500,
                      extra_headers={"Cache-Control": "no-store"})
            return

        # ── Render and return SVG ────────────────────────────────────────────
        try:
            svg = build_timeline_svg(stats)
        except Exception:
            error_svg = build_error_svg(
                "SVG rendering error",
                "Please try again later."
            )
            _send_svg(self, error_svg, status=500,
                      extra_headers={"Cache-Control": "no-store"})
            return

        _send_svg(self, svg, status=200)

    def log_message(self, fmt, *args):
        """
        Override default HTTP logging.
        Only log the response status — never log paths, usernames, or query strings.
        """
        status = args[1] if len(args) > 1 else "-"
        print(f"[api/stats] response={status}")
