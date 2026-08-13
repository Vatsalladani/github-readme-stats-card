"""
scripts/generate_stats.py
--------------------------
Local / GitHub Actions entry point for github-readme-stats-card.

Reads:
  GITHUB_TOKEN    – required (GitHub personal access token)
  GITHUB_USERNAME – optional (defaults to "Vatsalladani")

Writes:
  assets/stats_data.json   – full stats for use by generate_animation.py
  assets/github-stats.svg  – the rendered Developer Timeline card

This script is NOT the public API endpoint. It is only for:
  1. Local development / manual regeneration
  2. The GitHub Actions workflow (.github/workflows/update-stats.yml)

The shared logic lives in:
  lib/stats_engine.py  – data fetching and calculation
  lib/svg_renderer.py  – SVG rendering

Usage:
  python scripts/generate_stats.py

Environment:
  GITHUB_TOKEN     (required) – GitHub PAT with read:user + repo scopes
  GITHUB_USERNAME  (optional) – GitHub login to generate stats for
"""

import os
import sys
import json

# Allow running from the repo root or the scripts/ subdirectory
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from lib.stats_engine import build_stats
from lib.svg_renderer import build_timeline_svg


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

TOKEN    = os.environ.get("GITHUB_TOKEN")
USERNAME = os.environ.get("GITHUB_USERNAME", "Vatsalladani")

if not TOKEN:
    raise SystemExit("ERROR: GITHUB_TOKEN environment variable is not set.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print(f"Generating stats for: {USERNAME}")
    print("Fetching data from GitHub GraphQL API...")

    try:
        stats = build_stats(USERNAME, TOKEN)
    except ValueError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc
    except RuntimeError as exc:
        raise SystemExit(f"ERROR: {exc}") from exc

    print(f"  Login:               {stats['login']}")
    print(f"  Total contributions: {stats['total_contributions']}")
    print(f"  Current streak:      {stats['current_streak']} days ({stats['current_streak_range']})")
    print(f"  Longest streak:      {stats['longest_streak']} days ({stats['longest_streak_range']})")
    print(f"  Peak day:            {stats['peak_date']} ({stats['peak_count']} contributions)")
    print(f"  Top month:           {stats['top_month']} ({stats['top_month_total']} contributions)")
    print(f"  History start:       {stats['history_start']}")
    print(f"  Yearly activity:     {stats['yearly_activity']}")

    # Write assets/stats_data.json
    os.makedirs("assets", exist_ok=True)
    json_path = "assets/stats_data.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(stats, f, indent=2)
    print(f"\nWrote: {json_path}")

    # Write assets/github-stats.svg
    svg_content = build_timeline_svg(stats)
    svg_path = "assets/github-stats.svg"
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Wrote: {svg_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()