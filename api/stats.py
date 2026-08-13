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

# Add repo root to sys.path so lib/ is importable in Vercel's sandbox
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from lib.stats_engine import build_stats
from lib.svg_renderer import build_timeline_svg, build_error_svg


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# GitHub's documented login format: alphanumeric + hyphens, 1–39 chars,
# cannot start or end with a hyphen, no consecutive hyphens.
# We use a slightly permissive regex here (allows leading/trailing hyphens)
# and rely on the GitHub API itself to reject truly invalid logins.
_USERNAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9-]{0,37}[a-zA-Z0-9]$|^[a-zA-Z0-9]$')

_SVG_CONTENT_TYPE = "image/svg+xml; charset=utf-8"

_CACHE_CONTROL = "public, s-maxage=3600, stale-while-revalidate=86400"


def _get_token():
    """
    Read GITHUB_TOKEN from the server-side environment.

    Raises RuntimeError if the variable is absent (misconfigured deployment).
    The token is NEVER returned to callers or included in any response.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        raise RuntimeError(
            "GITHUB_TOKEN is not configured in the deployment environment."
        )
    return token


def _validate_username(username):
    """
    Validate that a username matches GitHub's login format.

    Returns (True, "") on success.
    Returns (False, reason_string) on failure — reason is user-visible and
    must NOT contain internal details.
    """
    if not username:
        return False, "username is required"
    if len(username) > 39:
        return False, "username too long (max 39 characters)"
    if not _USERNAME_RE.match(username):
        return False, "invalid username format"
    return True, ""


def _send_svg(handler, svg_body, status=200, extra_headers=None):
    """Write an SVG HTTP response."""
    body = svg_body.encode("utf-8")

    handler.send_response(status)
    handler.send_header("Content-Type", _SVG_CONTENT_TYPE)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", _CACHE_CONTROL)
    handler.send_header("X-Content-Type-Options", "nosniff")
    if extra_headers:
        for key, value in extra_headers.items():
            handler.send_header(key, value)
    handler.end_headers()
    handler.wfile.write(body)


# ---------------------------------------------------------------------------
# Vercel serverless handler (BaseHTTPRequestHandler pattern)
# ---------------------------------------------------------------------------

class handler(BaseHTTPRequestHandler):
    """
    Vercel Python serverless function handler.

    Vercel auto-discovers this class in api/stats.py and routes
    GET /api/stats to do_GET().
    """

    def do_GET(self):
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
            # Deployment misconfiguration — don't expose details
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
            # User not found on GitHub — clean user-facing error
            error_svg = build_error_svg(
                f"GitHub user not found: {username}",
                "Check the spelling and try again."
            )
            _send_svg(self, error_svg, status=200,
                      extra_headers={"Cache-Control": "no-store"})
            return
        except RuntimeError as exc:
            # GitHub API error — surface a safe message only
            msg = str(exc)
            # Ensure we never accidentally include the token in the message
            safe_msg = msg if "token" not in msg.lower() else "GitHub API error"
            error_svg = build_error_svg(
                "GitHub API error",
                safe_msg[:80]
            )
            _send_svg(self, error_svg, status=200,
                      extra_headers={"Cache-Control": "no-store"})
            return
        except Exception:
            # Unexpected error — log nothing to response
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
        Omit request paths from logs to avoid accidentally logging usernames
        or any token fragments that might appear in query strings.
        We log only the response code and a fixed label.
        """
        # args[1] is the HTTP status code
        status = args[1] if len(args) > 1 else "-"
        print(f"[api/stats] response={status}")
