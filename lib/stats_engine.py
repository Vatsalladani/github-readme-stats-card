"""
lib/stats_engine.py
-------------------
Pure data-fetching and statistics calculation logic for github-readme-stats-card.

Used by:
  - scripts/generate_stats.py  (local / GitHub Actions)
  - api/stats.py               (Vercel serverless handler)

All public functions accept `token` as an explicit argument so there is NO
global state and NO hidden environment variable dependency in this module.
The caller (scripts/ or api/) is responsible for reading GITHUB_TOKEN from
the environment and passing it here.

No secrets, no hardcoded usernames, no hardcoded dates.
"""

import json
import urllib.request
import urllib.error
from collections import defaultdict
from datetime import date, timedelta


# ---------------------------------------------------------------------------
# GraphQL transport
# ---------------------------------------------------------------------------

GRAPHQL_URL = "https://api.github.com/graphql"


def graphql(query, variables, token):
    """
    Execute a GraphQL query against the GitHub API.

    Parameters
    ----------
    query     : str   – GraphQL query string
    variables : dict  – query variables
    token     : str   – GitHub personal access token (Bearer)

    Returns
    -------
    dict  – the ``data`` object from the JSON response

    Raises
    ------
    RuntimeError  – on HTTP errors or GraphQL-level errors
    """
    payload = json.dumps(
        {"query": query, "variables": variables or {}}
    ).encode("utf-8")

    request = urllib.request.Request(
        GRAPHQL_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type":  "application/json",
            "User-Agent":    "github-readme-stats-card/2.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(
            f"GitHub API HTTP error: {exc.code} {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"GitHub API network error: {exc.reason}"
        ) from exc

    if "errors" in result:
        # Surface the first error message only — never leak internal details
        msg = result["errors"][0].get("message", "Unknown GraphQL error")
        raise RuntimeError(f"GitHub GraphQL error: {msg}")

    return result["data"]


# ---------------------------------------------------------------------------
# Query: user metadata
# ---------------------------------------------------------------------------

_USER_INFO_QUERY = """
query($username: String!) {
  user(login: $username) {
    name
    login
    createdAt
    contributionsCollection {
      contributionYears
    }
  }
}
"""


def fetch_user_info(username, token):
    """
    Fetch a GitHub user's display name, login, account creation date,
    and the list of years in which they have contributions.

    Parameters
    ----------
    username : str – GitHub login (e.g. "torvalds")
    token    : str – GitHub personal access token

    Returns
    -------
    tuple: (name, login, created_at_str, contribution_years)
      name               : str  – display name (may be None)
      login              : str  – exact GitHub login (use this for card identity)
      created_at_str     : str  – account creation date "YYYY-MM-DD"
      contribution_years : list[int] – years with any contribution calendar entry

    Raises
    ------
    RuntimeError – if the user does not exist or the API call fails
    ValueError   – if the username is valid format but unknown to GitHub
    """
    data = graphql(_USER_INFO_QUERY, {"username": username}, token)

    if data.get("user") is None:
        raise ValueError(f"GitHub user not found: {username!r}")

    user = data["user"]
    name               = user.get("name")          # may be None
    login              = user["login"]              # exact casing from GitHub
    created_at_str     = user["createdAt"][:10]    # YYYY-MM-DD
    contribution_years = (
        user["contributionsCollection"]["contributionYears"]
    )
    return name, login, created_at_str, contribution_years


# ---------------------------------------------------------------------------
# Query: contribution calendar for a single ≤365-day window
# ---------------------------------------------------------------------------

_CONTRIBUTION_CHUNK_QUERY = """
query($username: String!, $from: DateTime!, $to: DateTime!) {
  user(login: $username) {
    contributionsCollection(from: $from, to: $to) {
      contributionCalendar {
        weeks {
          contributionDays {
            date
            contributionCount
          }
        }
      }
    }
  }
}
"""


def _fetch_contribution_chunk(username, token, chunk_from, chunk_to):
    """
    Fetch one ≤365-day window of contribution data.

    Returns a list of dicts: [{"date": "YYYY-MM-DD", "count": int}, ...]
    Only days within [chunk_from, chunk_to] inclusive are returned.
    """
    data = graphql(
        _CONTRIBUTION_CHUNK_QUERY,
        {
            "username": username,
            "from":     f"{chunk_from.isoformat()}T00:00:00Z",
            "to":       f"{chunk_to.isoformat()}T23:59:59Z",
        },
        token,
    )

    if data.get("user") is None:
        return []

    calendar = (
        data["user"]["contributionsCollection"]["contributionCalendar"]
    )

    chunk_days = []
    for week in calendar["weeks"]:
        for day in week["contributionDays"]:
            day_date = date.fromisoformat(day["date"])
            if chunk_from <= day_date <= chunk_to:
                chunk_days.append(
                    {"date": day["date"], "count": day["contributionCount"]}
                )
    return chunk_days


# ---------------------------------------------------------------------------
# Full lifetime contribution history
# ---------------------------------------------------------------------------

def fetch_all_contributions(username, token, from_date, to_date):
    """
    Fetch all contributions for ``username`` from ``from_date`` to ``to_date``
    by issuing ≤365-day GraphQL chunks (GitHub's API limit).

    Returns a deduplicated, chronologically sorted list:
      [{"date": "YYYY-MM-DD", "count": int}, ...]

    A cache miss against this function may require multiple GraphQL requests
    depending on how many calendar years the user's history spans.
    """
    all_days   = {}   # date string → count (deduplicates overlap)
    chunk_from = from_date
    chunk_num  = 0

    while chunk_from <= to_date:
        chunk_num += 1
        chunk_to = min(chunk_from + timedelta(days=364), to_date)
        for day in _fetch_contribution_chunk(username, token, chunk_from, chunk_to):
            all_days[day["date"]] = day["count"]
        chunk_from = chunk_to + timedelta(days=1)

    return [
        {"date": d, "count": c}
        for d, c in sorted(all_days.items())
    ]


# ---------------------------------------------------------------------------
# Statistics calculations
# ---------------------------------------------------------------------------

def calculate_current_streak(contribution_map):
    """
    Count consecutive contribution days ending at the most recent date.

    If the most recent date has zero contributions, yesterday is checked so
    an active streak is not prematurely broken before the day ends.

    Parameters
    ----------
    contribution_map : dict[date, int]

    Returns
    -------
    (streak_length, streak_start, streak_end)  – all None if no active streak
    """
    if not contribution_map:
        return 0, None, None

    latest    = max(contribution_map)
    check_day = latest

    if contribution_map.get(check_day, 0) == 0:
        check_day = latest - timedelta(days=1)

    if contribution_map.get(check_day, 0) == 0:
        return 0, None, None

    streak       = 0
    streak_end   = check_day
    streak_start = check_day

    while contribution_map.get(check_day, 0) > 0:
        streak      += 1
        streak_start = check_day
        check_day   -= timedelta(days=1)

    return streak, streak_start, streak_end


def calculate_longest_streak(contribution_map):
    """
    Find the longest unbroken run of days with at least one contribution.

    Returns
    -------
    (streak_length, streak_start, streak_end)
    """
    longest       = 0
    longest_start = None
    longest_end   = None
    run_start     = None
    run_length    = 0
    prev_day      = None

    for day in sorted(contribution_map):
        if contribution_map[day] > 0:
            if run_start is None:
                run_start  = day
                run_length = 1
            elif prev_day is not None and day == prev_day + timedelta(days=1):
                run_length += 1
            else:
                run_start  = day
                run_length = 1

            if run_length > longest:
                longest       = run_length
                longest_start = run_start
                longest_end   = day
        else:
            run_start  = None
            run_length = 0

        prev_day = day

    return longest, longest_start, longest_end


def format_streak_range(start_date, end_date):
    """
    Format a date range as "Aug 6 - Aug 12" (same-year) or
    "Dec 29, 2024 - Jan 3, 2025" (cross-year).
    Returns empty string if either date is None.
    """
    if not start_date or not end_date:
        return ""
    if start_date.year == end_date.year:
        s = start_date.strftime("%b %d").replace(" 0", " ")
        e = end_date.strftime("%b %d").replace(" 0", " ")
    else:
        s = start_date.strftime("%b %d, %Y").replace(" 0", " ")
        e = end_date.strftime("%b %d, %Y").replace(" 0", " ")
    return f"{s} - {e}"


def calculate_yearly_activity(days, contribution_years):
    """
    Aggregate contributions by calendar year.

    Every year in ``contribution_years`` is always included, even if it has
    zero contributions, so the timeline is continuous and predictable.
    Future years are automatically included once GitHub returns them.

    Parameters
    ----------
    days               : list[{"date": str, "count": int}]
    contribution_years : list[int]

    Returns
    -------
    dict[int, int]  – {year: total_contributions}, sorted ascending
    """
    by_year = defaultdict(int)

    for day in days:
        year = int(day["date"][:4])
        by_year[year] += day["count"]

    # Ensure every year GitHub knows about is represented (zeros included)
    for year in contribution_years:
        if year not in by_year:
            by_year[year] = 0

    return dict(sorted(by_year.items()))


# ---------------------------------------------------------------------------
# High-level: build the complete stats dict for a username
# ---------------------------------------------------------------------------

def build_stats(username, token):
    """
    Fetch all GitHub data for ``username`` and return a fully-populated
    stats dict ready to be passed to ``svg_renderer.build_timeline_svg()``.

    This is the single public entry point that ``api/stats.py`` should call.

    Raises
    ------
    ValueError   – user not found on GitHub
    RuntimeError – API / network failure
    """
    today = date.today()

    name, login, account_created_str, contribution_years = fetch_user_info(
        username, token
    )

    if not contribution_years:
        # New account with no contribution calendar yet — return zeroed stats
        return {
            "username":              login,
            "name":                  name,
            "login":                 login,
            "display_name":          login,
            "account_created":       account_created_str,
            "total_contributions":   0,
            "current_streak":        0,
            "current_streak_start":  None,
            "current_streak_end":    None,
            "current_streak_range":  "",
            "longest_streak":        0,
            "longest_streak_start":  None,
            "longest_streak_end":    None,
            "longest_streak_range":  "",
            "peak_date":             account_created_str,
            "peak_count":            0,
            "top_month":             account_created_str[:7],
            "top_month_total":       0,
            "history_start":         account_created_str,
            "history_end":           today.isoformat(),
            "yearly_activity":       {},
        }

    earliest_year = min(contribution_years)
    from_date     = date(earliest_year, 1, 1)
    to_date       = today

    days = fetch_all_contributions(username, token, from_date, to_date)

    # Determine real contribution boundaries
    contributing_days = [d for d in days if d["count"] > 0]
    if contributing_days:
        history_start_str = contributing_days[0]["date"]
        history_end_str   = contributing_days[-1]["date"]
    else:
        history_start_str = days[0]["date"] if days else account_created_str
        history_end_str   = today.isoformat()

    total_contributions = sum(d["count"] for d in days)

    contribution_map = {
        date.fromisoformat(d["date"]): d["count"] for d in days
    }

    cur_streak, cur_start, cur_end = calculate_current_streak(contribution_map)
    lng_streak, lng_start, lng_end = calculate_longest_streak(contribution_map)
    cur_range = format_streak_range(cur_start, cur_end)
    lng_range = format_streak_range(lng_start, lng_end)

    peak_day = max(days, key=lambda d: d["count"]) if days else {"date": history_start_str, "count": 0}

    monthly = defaultdict(int)
    for d in days:
        monthly[d["date"][:7]] += d["count"]
    top_month_key   = max(monthly, key=monthly.get) if monthly else account_created_str[:7]
    top_month_total = monthly[top_month_key] if monthly else 0

    yearly_activity = calculate_yearly_activity(days, contribution_years)

    return {
        "username":              login,        # login is the identity
        "name":                  name,
        "login":                 login,
        "display_name":          login,
        "account_created":       account_created_str,
        "total_contributions":   total_contributions,
        "current_streak":        cur_streak,
        "current_streak_start":  cur_start.isoformat() if cur_start else None,
        "current_streak_end":    cur_end.isoformat() if cur_end else None,
        "current_streak_range":  cur_range,
        "longest_streak":        lng_streak,
        "longest_streak_start":  lng_start.isoformat() if lng_start else None,
        "longest_streak_end":    lng_end.isoformat() if lng_end else None,
        "longest_streak_range":  lng_range,
        "peak_date":             peak_day["date"],
        "peak_count":            peak_day["count"],
        "top_month":             top_month_key,
        "top_month_total":       top_month_total,
        "history_start":         history_start_str,
        "history_end":           history_end_str,
        "yearly_activity":       yearly_activity,
    }
