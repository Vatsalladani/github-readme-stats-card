"""
lib/svg_renderer.py
-------------------
SVG rendering for github-readme-stats-card.

Used by:
  - scripts/generate_stats.py  (local / GitHub Actions)
  - api/stats.py               (Vercel serverless handler)

``build_timeline_svg(stats)``  — render the full approved card design.
``build_error_svg(message)``   — render a clean error card (no stack traces).

The visual design is the canonical approved design. Do NOT change dimensions,
colors, typography, spacing, or structural elements here without an explicit
design decision. This renderer simply populates the design with caller-supplied
data.
"""

from datetime import datetime


# ---------------------------------------------------------------------------
# SVG escaping
# ---------------------------------------------------------------------------

def escape_svg(value):
    """Escape characters that are special in XML/SVG attribute/text nodes."""
    return (
        str(value)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )


# ---------------------------------------------------------------------------
# Main card renderer — approved Developer Timeline design
# ---------------------------------------------------------------------------

def build_timeline_svg(stats):
    """
    Render the approved Developer Timeline SVG card from a stats dict.

    Parameters
    ----------
    stats : dict
        Must contain all keys produced by ``lib.stats_engine.build_stats()``.

    Returns
    -------
    str  – complete SVG document string
    """
    W, H    = 820, 340
    PAD     = 36
    INNER_W = W - PAD * 2   # 748

    login         = escape_svg(stats.get("login") or stats.get("username", ""))
    username      = escape_svg(stats.get("username", login))

    total         = stats["total_contributions"]
    cur_streak    = stats["current_streak"]
    cur_range     = escape_svg(stats.get("current_streak_range", ""))
    lng_streak    = stats["longest_streak"]
    lng_range     = escape_svg(stats.get("longest_streak_range", ""))
    peak_date_str = stats["peak_date"]
    peak_count    = stats["peak_count"]
    top_month_str = stats["top_month"]
    top_month_tot = stats["top_month_total"]
    history_start = stats["history_start"]
    yearly        = stats.get("yearly_activity") or {}

    # Formatted labels
    _pd = datetime.strptime(peak_date_str, "%Y-%m-%d")
    peak_label = _pd.strftime("%b %d, %Y").replace(" 0", " ")

    month_label = datetime.strptime(
        top_month_str + "-01", "%Y-%m-%d"
    ).strftime("%b %Y")

    _hs = datetime.strptime(history_start, "%Y-%m-%d")
    history_start_formatted = _hs.strftime("%b %d, %Y").replace(" 0", " ")

    # ── Timeline geometry ────────────────────────────────────────────────────
    years   = sorted(yearly.keys())
    n_years = len(years)

    max_count = max(yearly.values()) if yearly else 1
    BAR_MAX_H = 22
    BAR_W     = max(4, min(16, int(INNER_W / max(n_years, 1)) - 8))

    TL_Y          = 122
    TL_LEFT       = PAD + 20
    TL_RIGHT      = W - PAD - 20
    TL_W          = TL_RIGHT - TL_LEFT
    TL_NODE_RIGHT = TL_LEFT + int(TL_W * 0.78)

    def year_x(i):
        if n_years <= 1:
            return TL_LEFT + int(TL_W * 0.30)
        return int(TL_LEFT + (i / (n_years - 1)) * (TL_NODE_RIGHT - TL_LEFT))

    # ── Year nodes + bars ────────────────────────────────────────────────────
    year_elements = []
    for i, year in enumerate(years):
        cx      = year_x(i)
        cnt     = yearly[year]
        is_zero = (cnt == 0)

        bar_html = ""
        if max_count > 0 and not is_zero:
            bh    = max(3, int((cnt / max_count) * BAR_MAX_H))
            bar_x = cx - BAR_W // 2
            bar_y = TL_Y - 14 - bh
            rx_v  = 2 if bh <= 5 else 4
            bar_html = (
                f'<rect x="{bar_x}" y="{bar_y}" width="{BAR_W}" height="{bh}"'
                f' rx="{rx_v}" fill="#1f6feb"/>'
            )

        year_elements.append(
            f'\n    <!-- Year {year} -->'
            f'\n    {bar_html}'
            f'\n    <circle cx="{cx}" cy="{TL_Y}" r="5"'
            f' fill="#388bfd" stroke="#0d1117" stroke-width="2"/>'
            f'\n    <text x="{cx}" y="{TL_Y + 20}" text-anchor="middle"'
            f' fill="#388bfd"'
            f' font-family="ui-monospace,\'Cascadia Code\',Consolas,monospace"'
            f' font-size="10" font-weight="700">{year}</text>'
        )

    year_nodes_svg = "\n".join(year_elements)

    now_x = TL_RIGHT
    now_element = (
        f'<circle cx="{now_x}" cy="{TL_Y}" r="4"'
        f' fill="#3fb950" stroke="#0d1117" stroke-width="2"/>'
        f'\n    <text x="{now_x}" y="{TL_Y + 20}" text-anchor="middle"'
        f' fill="#3fb950"'
        f' font-family="ui-monospace,\'Cascadia Code\',Consolas,monospace"'
        f' font-size="9" font-weight="700">NOW</text>'
    )

    # ── Column x positions ───────────────────────────────────────────────────
    cx1 = 156
    cx2 = 406
    cx3 = 660

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg"
     width="{W}" height="{H}" viewBox="0 0 {W} {H}"
     role="img" aria-label="GitHub Developer Timeline for {login}">

  <title>{login} · GitHub Developer Timeline</title>

  <defs>
    <linearGradient id="accentGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%"   stop-color="#388bfd"/>
      <stop offset="60%"  stop-color="#a371f7"/>
      <stop offset="100%" stop-color="#388bfd" stop-opacity="0.3"/>
    </linearGradient>
    <clipPath id="cardClip">
      <rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14"/>
    </clipPath>
  </defs>

  <!-- Card background -->
  <rect x="1" y="1" width="{W-2}" height="{H-2}"
        rx="14" fill="#0d1117" stroke="#21262d" stroke-width="1"/>

  <!-- Top accent line -->
  <rect x="1" y="1" width="{W-2}" height="2"
        rx="1" fill="url(#accentGrad)" clip-path="url(#cardClip)"/>

  <!-- ── HEADER ── -->
  <text x="{PAD}" y="38"
        fill="#f0f6fc"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="20" font-weight="700">{login}</text>

  <text x="{PAD}" y="57"
        fill="#8b949e"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="12">Developer Timeline</text>

  <!-- project name top-right -->
  <text x="{W - PAD}" y="38" text-anchor="end"
        fill="#6e7681"
        font-family="ui-monospace,'Cascadia Code',Consolas,monospace"
        font-size="10">github-readme-stats-card</text>

  <!-- ── DIVIDER 1 ── -->
  <line x1="{PAD}" y1="70" x2="{W - PAD}" y2="70"
        stroke="#21262d" stroke-width="1"/>

  <!-- ── TIMELINE SECTION ── -->

  <!-- Timeline rail -->
  <line x1="{TL_LEFT}" y1="{TL_Y}" x2="{TL_RIGHT}" y2="{TL_Y}"
        stroke="#30363d" stroke-width="2"/>

  {year_nodes_svg}
  {now_element}

  <!-- ── DIVIDER 2 ── -->
  <line x1="{PAD}" y1="160" x2="{W - PAD}" y2="160"
        stroke="#21262d" stroke-width="1"/>

  <!-- ── PRIMARY STATS (3 Columns with Subtle Vertical Dividers) ── -->

  <!-- Vertical column dividers -->
  <line x1="276" y1="168" x2="276" y2="262" stroke="#21262d" stroke-width="1"/>
  <line x1="536" y1="168" x2="536" y2="262" stroke="#21262d" stroke-width="1"/>

  <!-- Column 1: Total Contributions -->
  <text x="{cx1}" y="200" text-anchor="middle"
        fill="#f0f6fc"
        font-family="ui-monospace,'Cascadia Code',Consolas,monospace"
        font-size="38" font-weight="700">{total}</text>
  <text x="{cx1}" y="228" text-anchor="middle"
        fill="#8b949e"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="10" font-weight="700" letter-spacing="0.5">CONTRIBUTIONS</text>
  <text x="{cx1}" y="244" text-anchor="middle"
        fill="#6e7681"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="9">Since {history_start_formatted}</text>

  <!-- Column 2: Current Streak (Circular Green Ring + Blue Flame) -->
  <circle cx="{cx2}" cy="193" r="17" fill="none" stroke="#3fb950" stroke-width="2"/>
  <g transform="translate({cx2}, 169)">
    <path d="M 0,-7 C 2,-3.5 4.5,-2 4.5,1.5 C 4.5,4.5 2.5,6.5 0,6.5 C -2.5,6.5 -4.5,4.5 -4.5,1.5 C -4.5,-2 -2,-3.5 0,-7 Z" fill="#388bfd"/>
    <path d="M 0,-3 C 1,-1 2,0 2,1.8 C 2,3.2 1,4 0,4 C -1,4 -2,3.2 -2,1.8 C -2,0 -1,-1 0,-3 Z" fill="#58a6ff"/>
  </g>
  <text x="{cx2}" y="199" text-anchor="middle"
        fill="#3fb950"
        font-family="ui-monospace,'Cascadia Code',Consolas,monospace"
        font-size="18" font-weight="700">{cur_streak}</text>
  <text x="{cx2}" y="228" text-anchor="middle"
        fill="#8b949e"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="10" font-weight="700" letter-spacing="0.5">CURRENT STREAK</text>
  <text x="{cx2}" y="244" text-anchor="middle"
        fill="#6e7681"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="9">consecutive days</text>
  <text x="{cx2}" y="258" text-anchor="middle"
        fill="#3fb950"
        font-family="ui-monospace,'Cascadia Code',Consolas,monospace"
        font-size="9" font-weight="700">{cur_range}</text>

  <!-- Column 3: Longest Streak -->
  <text x="{cx3}" y="200" text-anchor="middle"
        fill="#a371f7"
        font-family="ui-monospace,'Cascadia Code',Consolas,monospace"
        font-size="38" font-weight="700">{lng_streak}</text>
  <text x="{cx3}" y="228" text-anchor="middle"
        fill="#8b949e"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="10" font-weight="700" letter-spacing="0.5">LONGEST STREAK</text>
  <text x="{cx3}" y="244" text-anchor="middle"
        fill="#6e7681"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="9">personal best</text>
  <text x="{cx3}" y="258" text-anchor="middle"
        fill="#a371f7"
        font-family="ui-monospace,'Cascadia Code',Consolas,monospace"
        font-size="9" font-weight="700">{lng_range}</text>

  <!-- ── DIVIDER 3 ── -->
  <line x1="{PAD}" y1="270" x2="{W - PAD}" y2="270"
        stroke="#21262d" stroke-width="1"/>

  <!-- ── INSIGHTS ROW ── -->

  <!-- Peak Day -->
  <text x="{PAD}" y="286"
        fill="#6e7681"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="9" font-weight="700" letter-spacing="0.5">PEAK DAY</text>
  <text x="{PAD}" y="303"
        font-family="ui-monospace,'Cascadia Code',Consolas,monospace"
        font-size="11"><tspan fill="#f0f6fc">{peak_label}</tspan><tspan fill="#6e7681">  ·  </tspan><tspan fill="#a371f7" font-weight="700">{peak_count}</tspan></text>

  <!-- Top Month -->
  <text x="316" y="286"
        fill="#6e7681"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="9" font-weight="700" letter-spacing="0.5">TOP MONTH</text>
  <text x="316" y="303"
        font-family="ui-monospace,'Cascadia Code',Consolas,monospace"
        font-size="11"><tspan fill="#f0f6fc">{month_label}</tspan><tspan fill="#6e7681">  ·  </tspan><tspan fill="#a371f7" font-weight="700">{top_month_tot}</tspan></text>

  <!-- First Activity -->
  <text x="596" y="286"
        fill="#6e7681"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="9" font-weight="700" letter-spacing="0.5">FIRST ACTIVITY</text>
  <text x="596" y="303"
        fill="#f0f6fc"
        font-family="ui-monospace,'Cascadia Code',Consolas,monospace"
        font-size="11">{history_start_formatted}</text>

  <!-- ── FOOTER ── -->
  <text x="{W - PAD}" y="325" text-anchor="end"
        fill="#6e7681"
        font-family="ui-monospace,'Cascadia Code',Consolas,monospace"
        font-size="9">github-readme-stats-card · by {login}</text>

</svg>'''

    return svg


# ---------------------------------------------------------------------------
# Error card renderer
# ---------------------------------------------------------------------------

def build_error_svg(message, detail=""):
    """
    Render a clean error card that matches the main card's visual language.

    Parameters
    ----------
    message : str  – short primary error message (user-visible)
    detail  : str  – optional secondary line (must NOT contain secrets)

    Returns
    -------
    str  – complete SVG document string

    IMPORTANT: Never pass token values, stack traces, or internal paths
    to this function. Both ``message`` and ``detail`` are rendered into
    the SVG that will be served publicly.
    """
    W, H = 820, 200
    PAD  = 36

    safe_message = escape_svg(message[:120])   # cap length
    safe_detail  = escape_svg(detail[:120]) if detail else ""

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg"
     width="{W}" height="{H}" viewBox="0 0 {W} {H}"
     role="img" aria-label="GitHub Stats Card — Error">

  <title>GitHub Stats Card — Error</title>

  <defs>
    <linearGradient id="accentGrad" x1="0" y1="0" x2="1" y2="0">
      <stop offset="0%"   stop-color="#f85149"/>
      <stop offset="60%"  stop-color="#a371f7"/>
      <stop offset="100%" stop-color="#f85149" stop-opacity="0.3"/>
    </linearGradient>
    <clipPath id="cardClip">
      <rect x="1" y="1" width="{W-2}" height="{H-2}" rx="14"/>
    </clipPath>
  </defs>

  <!-- Card background -->
  <rect x="1" y="1" width="{W-2}" height="{H-2}"
        rx="14" fill="#0d1117" stroke="#21262d" stroke-width="1"/>

  <!-- Top accent line (red for error) -->
  <rect x="1" y="1" width="{W-2}" height="2"
        rx="1" fill="url(#accentGrad)" clip-path="url(#cardClip)"/>

  <!-- Header -->
  <text x="{PAD}" y="38"
        fill="#f0f6fc"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="20" font-weight="700">github-readme-stats-card</text>

  <text x="{PAD}" y="57"
        fill="#8b949e"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="12">Developer Timeline</text>

  <!-- Divider -->
  <line x1="{PAD}" y1="70" x2="{W - PAD}" y2="70"
        stroke="#21262d" stroke-width="1"/>

  <!-- Error icon (⚠) -->
  <text x="{W // 2}" y="118" text-anchor="middle"
        fill="#f85149" font-size="28">⚠</text>

  <!-- Error message -->
  <text x="{W // 2}" y="148" text-anchor="middle"
        fill="#f0f6fc"
        font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif"
        font-size="14" font-weight="600">{safe_message}</text>

  <!-- Detail line (if any) -->
  {'<text x="' + str(W // 2) + '" y="170" text-anchor="middle" fill="#8b949e" font-family="system-ui,-apple-system,BlinkMacSystemFont,Arial,sans-serif" font-size="11">' + safe_detail + '</text>' if safe_detail else ''}

  <!-- Footer -->
  <text x="{W - PAD}" y="{H - 15}" text-anchor="end"
        fill="#6e7681"
        font-family="ui-monospace,'Cascadia Code',Consolas,monospace"
        font-size="9">github-readme-stats-card</text>

</svg>'''

    return svg
