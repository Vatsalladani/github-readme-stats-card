"""
generate_animation.py
---------------------
Reads assets/stats_data.json and produces assets/github-stats.gif.

Animation philosophy:
  - Subtle, professional reveal — not a demo/toy
  - Every data point comes from stats_data.json (no fabricated values)
  - Four phases:
      Phase 1 (frames  0–10): Accent line draws left → right
      Phase 2 (frames 11–20): Timeline rail + nodes/bars appear left → right
      Phase 3 (frames 21–28): Stat numbers + text fade in cleanly
      Phase 4 (frames 29–44): Stable hold (most of the GIF)

Total: 45 frames @ 60 ms = ~2.7 s loop, then hold on last frame via loop=0.
The card is pixel-identical to the SVG design in final state.
"""

import json
import os
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

# ---------------------------------------------------------------------------
# Load stats
# ---------------------------------------------------------------------------

STATS_PATH = Path("assets/stats_data.json")
if not STATS_PATH.exists():
    raise SystemExit("ERROR: assets/stats_data.json not found. Run generate_stats.py first.")

with open(STATS_PATH, encoding="utf-8") as f:
    S = json.load(f)

USERNAME          = S["username"]
LOGIN             = S.get("login", USERNAME)
TOTAL             = S["total_contributions"]
CUR_STREAK        = S["current_streak"]
CUR_RANGE         = S.get("current_streak_range", "")
LNG_STREAK        = S["longest_streak"]
LNG_RANGE         = S.get("longest_streak_range", "")
PEAK_DATE         = S["peak_date"]
PEAK_COUNT        = S["peak_count"]
TOP_MONTH         = S["top_month"]
TOP_MONTH_TOTAL   = S["top_month_total"]
HISTORY_START     = S["history_start"]
HISTORY_END       = S["history_end"]
YEARLY            = S["yearly_activity"]  # {str_year: int}

# Formatted display labels
_pd_dt      = datetime.strptime(PEAK_DATE, "%Y-%m-%d")
PEAK_LABEL  = _pd_dt.strftime("%b %d, %Y").replace(" 0", " ")
MONTH_LABEL = datetime.strptime(TOP_MONTH + "-01", "%Y-%m-%d").strftime("%b %Y")
_hs_dt      = datetime.strptime(HISTORY_START, "%Y-%m-%d")
HISTORY_START_LABEL = _hs_dt.strftime("%b %d, %Y").replace(" 0", " ")

YEARS = sorted(int(y) for y in YEARLY)
YEAR_COUNTS = [YEARLY[str(y)] for y in YEARS]

# ---------------------------------------------------------------------------
# Canvas / layout constants  (must mirror SVG)
# ---------------------------------------------------------------------------

W, H  = 820, 340
PAD   = 36

# Timeline
TL_Y          = 122
TL_LEFT       = PAD + 20
TL_RIGHT      = W - PAD - 20
TL_W          = TL_RIGHT - TL_LEFT
TL_NODE_RIGHT = TL_LEFT + int(TL_W * 0.78)  # rightmost year node

N_YEARS  = len(YEARS)
MAX_CNT  = max(YEAR_COUNTS) if YEAR_COUNTS else 1
BAR_MAX  = 22
BAR_W    = max(4, min(16, int((TL_NODE_RIGHT - TL_LEFT) / max(N_YEARS, 1)) - 8))


def year_x(i):
    if N_YEARS <= 1:
        return TL_LEFT + int(TL_W * 0.30)
    return int(TL_LEFT + (i / (N_YEARS - 1)) * (TL_NODE_RIGHT - TL_LEFT))


YEAR_XS     = [year_x(i) for i in range(N_YEARS)]
LAST_YEAR_X = YEAR_XS[-1] if YEAR_XS else TL_LEFT

# Column centers
CX1 = 156
CX2 = 406
CX3 = 660

# ---------------------------------------------------------------------------
# Colors  (GitHub dark palette)
# ---------------------------------------------------------------------------

BG           = (13, 17, 23)
CARD_BG      = (13, 17, 23)
BORDER       = (33, 38, 45)
ACCENT_BLUE  = (56, 139, 253)
ACCENT_PURP  = (163, 113, 247)
ACCENT_GREEN = (63, 185, 80)
TEXT_PRI     = (240, 246, 252)
TEXT_SEC     = (139, 148, 158)
TEXT_MUT     = (110, 118, 129)
TEXT_DIM     = (110, 118, 129)
BAR_FILL     = (31, 111, 235)
RAIL         = (48, 54, 61)

# ---------------------------------------------------------------------------
# Font helpers
# ---------------------------------------------------------------------------

_FONTS_DIR = Path(__file__).parent.parent / "assets" / "fonts"

_JBM_REGULAR    = str(_FONTS_DIR / "JetBrainsMono-Regular.ttf")
_JBM_BOLD       = str(_FONTS_DIR / "JetBrainsMono-Bold.ttf")
_JBM_EXTRALIGHT = str(_FONTS_DIR / "JetBrainsMono-ExtraLight.ttf")


def _load_font(path, size):
    """Load a bundled TTF, falling back to Pillow default only if file missing."""
    if Path(path).exists():
        return ImageFont.truetype(path, size)
    print(f"WARNING: bundled font not found: {path}  — using fallback", flush=True)
    return ImageFont.load_default()


def mono(size, bold=False):
    """Monospace font — JetBrains Mono Regular or Bold."""
    return _load_font(_JBM_BOLD if bold else _JBM_REGULAR, size)


def sans(size, bold=False):
    """Label font — uses JetBrains Mono ExtraLight for body labels, Bold for headings."""
    return _load_font(_JBM_BOLD if bold else _JBM_EXTRALIGHT, size)


F_USERNAME   = sans(20, bold=True)
F_SUBTITLE   = sans(12)
F_LABEL_SM   = sans(10, bold=True)
F_LABEL_XS   = sans(9)
F_NUMBER     = mono(38, bold=True)
F_RING_NUM   = mono(18, bold=True)
F_MONO_SM    = mono(11)
F_YEAR       = mono(10, bold=True)
F_FOOTER     = mono(9)
F_BRAND      = mono(10)

# ---------------------------------------------------------------------------
# Animation config
# ---------------------------------------------------------------------------

FRAME_COUNT    = 45
FRAME_DURATION = 60   # ms per frame

# Phase boundaries (frame indices, inclusive)
PH1_START, PH1_END = 0, 10   # accent line draws
PH2_START, PH2_END = 11, 22  # timeline reveals
PH3_START, PH3_END = 23, 32  # stats reveal
PH4_START, PH4_END = 33, 44  # stable hold


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def ease_out(t):
    t = clamp(t, 0.0, 1.0)
    return 1.0 - (1.0 - t) ** 3


def phase_progress(frame_i, start, end):
    """0.0 → 1.0 progress within a phase."""
    if end == start:
        return 1.0 if frame_i >= start else 0.0
    return clamp((frame_i - start) / (end - start), 0.0, 1.0)


def alpha_color(color, alpha):
    """Return color with alpha blended onto BG."""
    r = int(BG[0] + (color[0] - BG[0]) * alpha)
    g = int(BG[1] + (color[1] - BG[1]) * alpha)
    b = int(BG[2] + (color[2] - BG[2]) * alpha)
    return (r, g, b)


# ---------------------------------------------------------------------------
# Rounded rect helper (Pillow >= 8.2)
# ---------------------------------------------------------------------------

def draw_card(draw, x1, y1, x2, y2, fill=CARD_BG, outline=BORDER, radius=14):
    draw.rounded_rectangle((x1, y1, x2, y2), radius=radius,
                            fill=fill, outline=outline, width=1)


# ---------------------------------------------------------------------------
# Draw a single frame
# ---------------------------------------------------------------------------

def draw_frame(frame_i):
    img  = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)

    # ── Card background + border ──────────────────────────────────────────
    draw_card(draw, 1, 1, W - 1, H - 1, fill=CARD_BG, outline=BORDER, radius=14)

    # ── Phase 1: Accent line draws left → right ───────────────────────────
    p1 = ease_out(phase_progress(frame_i, PH1_START, PH1_END))
    accent_right = int(PAD + p1 * (W - 2 * PAD))
    if accent_right > PAD:
        draw.line((PAD, 2, accent_right, 2), fill=ACCENT_BLUE, width=2)

    # ── Header (static once visible) ─────────────────────────────────────
    header_alpha = ease_out(phase_progress(frame_i, PH1_START + 3, PH1_END))
    if header_alpha > 0:
        draw.text((PAD, 18), LOGIN,
                  font=F_USERNAME, fill=alpha_color(TEXT_PRI, header_alpha))
        draw.text((PAD, 44), "Developer Timeline",
                  font=F_SUBTITLE, fill=alpha_color(TEXT_SEC, header_alpha))
        draw.text((W - PAD, 22), "github-readme-stats-card",
                  font=F_BRAND, fill=alpha_color(TEXT_MUT, header_alpha),
                  anchor="ra")

    # ── Divider 1 ──────────────────────────────────────────────────────────
    if header_alpha >= 1.0:
        draw.line((PAD, 70, W - PAD, 70), fill=BORDER, width=1)

    # ── Phase 2: Timeline rail + nodes ───────────────────────────────────
    p2 = ease_out(phase_progress(frame_i, PH2_START, PH2_END))

    if p2 > 0:
        # Rail — draws proportionally across the entire baseline
        rail_right = int(TL_LEFT + p2 * TL_W)
        draw.line((TL_LEFT, TL_Y, rail_right, TL_Y), fill=RAIL, width=2)

        # Nodes: appear one by one as rail reaches each node's x position
        for i, (year, cx, cnt) in enumerate(zip(YEARS, YEAR_XS, YEAR_COUNTS)):
            node_frac = ((cx - TL_LEFT) / TL_W) if TL_W else 0
            node_alpha = ease_out(clamp((p2 - node_frac) / 0.12, 0.0, 1.0))
            if node_alpha <= 0:
                continue

            is_zero = (cnt == 0)
            # Bar height: ONLY draw if cnt > 0
            if MAX_CNT > 0 and not is_zero:
                bh = max(3, int((cnt / MAX_CNT) * BAR_MAX))
                bx = cx - BAR_W // 2
                by = TL_Y - 14 - bh
                bar_c = alpha_color(BAR_FILL, node_alpha)
                r_val = 2 if bh <= 5 else 4
                draw.rounded_rectangle((bx, by, bx + BAR_W, TL_Y - 14),
                                       radius=r_val, fill=bar_c)

            # Node circle
            nc = alpha_color(ACCENT_BLUE, node_alpha)
            draw.ellipse((cx - 5, TL_Y - 5, cx + 5, TL_Y + 5),
                         fill=nc, outline=BG, width=2)

            # Year label (in BLUE)
            yc = alpha_color(ACCENT_BLUE, node_alpha)
            draw.text((cx, TL_Y + 14), str(year),
                      font=F_YEAR, fill=yc, anchor="mt")

        # NOW dot — appears when rail almost complete
        now_alpha = ease_out(clamp((p2 - 0.94) / 0.06, 0.0, 1.0))
        if now_alpha > 0:
            nc_g = alpha_color(ACCENT_GREEN, now_alpha)
            draw.ellipse((TL_RIGHT - 4, TL_Y - 4, TL_RIGHT + 4, TL_Y + 4),
                         fill=nc_g, outline=BG, width=2)
            draw.text((TL_RIGHT, TL_Y + 14), "NOW",
                      font=F_YEAR, fill=nc_g, anchor="mt")

    # ── Divider 2 ──────────────────────────────────────────────────────────
    if p2 >= 1.0:
        draw.line((PAD, 160, W - PAD, 160), fill=BORDER, width=1)

    # ── Phase 3: Stats reveal ─────────────────────────────────────────────
    p3 = ease_out(phase_progress(frame_i, PH3_START, PH3_END))

    if p3 > 0:
        # Vertical dividers between 3 columns
        v_col = alpha_color(BORDER, p3)
        draw.line((276, 168, 276, 262), fill=v_col, width=1)
        draw.line((536, 168, 536, 262), fill=v_col, width=1)

        # Column 1: Total Contributions
        draw.text((CX1, 168), str(TOTAL), anchor="mt",
                  font=F_NUMBER, fill=alpha_color(TEXT_PRI, p3))
        draw.text((CX1, 218), "CONTRIBUTIONS", anchor="mt",
                  font=F_LABEL_SM, fill=alpha_color(TEXT_SEC, p3))
        draw.text((CX1, 235), f"Since {HISTORY_START_LABEL}", anchor="mt",
                  font=F_LABEL_XS, fill=alpha_color(TEXT_MUT, p3))

        # Column 2: Current Streak (with Circular Green Ring & Blue Flame)
        ring_c = alpha_color(ACCENT_GREEN, p3)
        draw.ellipse((CX2 - 17, 176, CX2 + 17, 210), outline=ring_c, width=2)
        flame_c = alpha_color(ACCENT_BLUE, p3)
        draw.polygon([(CX2, 162), (CX2 + 4.5, 169), (CX2 - 4.5, 169)], fill=flame_c)
        draw.text((CX2, 183), str(CUR_STREAK), anchor="mt",
                  font=F_RING_NUM, fill=ring_c)

        draw.text((CX2, 218), "CURRENT STREAK", anchor="mt",
                  font=F_LABEL_SM, fill=alpha_color(TEXT_SEC, p3))
        draw.text((CX2, 233), "consecutive days", anchor="mt",
                  font=F_LABEL_XS, fill=alpha_color(TEXT_MUT, p3))
        draw.text((CX2, 247), CUR_RANGE, anchor="mt",
                  font=F_LABEL_XS, fill=ring_c)

        # Column 3: Longest Streak
        purp_c = alpha_color(ACCENT_PURP, p3)
        draw.text((CX3, 168), str(LNG_STREAK), anchor="mt",
                  font=F_NUMBER, fill=purp_c)
        draw.text((CX3, 218), "LONGEST STREAK", anchor="mt",
                  font=F_LABEL_SM, fill=alpha_color(TEXT_SEC, p3))
        draw.text((CX3, 233), "personal best", anchor="mt",
                  font=F_LABEL_XS, fill=alpha_color(TEXT_MUT, p3))
        draw.text((CX3, 247), LNG_RANGE, anchor="mt",
                  font=F_LABEL_XS, fill=purp_c)

    # ── Divider 3 + Insights ──────────────────────────────────────────────
    ins_alpha = ease_out(phase_progress(frame_i, PH3_START + 4, PH3_END + 4))
    if ins_alpha > 0:
        draw.line((PAD, 270, W - PAD, 270),
                  fill=alpha_color(BORDER, ins_alpha), width=1)

        # Peak Day
        draw.text((PAD, 278), "PEAK DAY",
                  font=F_LABEL_XS, fill=alpha_color(TEXT_MUT, ins_alpha))
        draw.text((PAD, 293), f"{PEAK_LABEL}  \u00b7  {PEAK_COUNT}",
                  font=F_MONO_SM, fill=alpha_color(TEXT_PRI, ins_alpha))

        # Top Month
        draw.text((316, 278), "TOP MONTH",
                  font=F_LABEL_XS, fill=alpha_color(TEXT_MUT, ins_alpha))
        draw.text((316, 293), f"{MONTH_LABEL}  \u00b7  {TOP_MONTH_TOTAL}",
                  font=F_MONO_SM, fill=alpha_color(TEXT_PRI, ins_alpha))

        # First Activity
        draw.text((596, 278), "FIRST ACTIVITY",
                  font=F_LABEL_XS, fill=alpha_color(TEXT_MUT, ins_alpha))
        draw.text((596, 293), HISTORY_START_LABEL,
                  font=F_MONO_SM, fill=alpha_color(TEXT_PRI, ins_alpha))

    # ── Footer ────────────────────────────────────────────────────────────
    footer_alpha = ease_out(phase_progress(frame_i, PH3_END, PH4_START + 2))
    if footer_alpha > 0:
        draw.text((W - PAD, 320),
                  f"github-readme-stats-card \u00b7 by {USERNAME}",
                  font=F_FOOTER, fill=alpha_color(TEXT_MUT, footer_alpha),
                  anchor="ra")

    return img


# ---------------------------------------------------------------------------
# Build frames and save
# ---------------------------------------------------------------------------

print(f"Building {FRAME_COUNT} frames…")
frames = [draw_frame(i) for i in range(FRAME_COUNT)]

out = Path("assets/github-stats.gif")
out.parent.mkdir(parents=True, exist_ok=True)

frames[0].save(
    out,
    save_all=True,
    append_images=frames[1:],
    duration=FRAME_DURATION,
    loop=0,
    optimize=True,
)

print(f"Saved: {out}  ({len(frames)} frames @ {FRAME_DURATION} ms)")