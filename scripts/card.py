"""Render the live stat cards shown in the READMEs.

Writes assets/card-{dark,light}.svg (the numbers) and assets/recent-{dark,light}.svg
(latest app updates) from the metrics merge.py collects. Plain SVG with system
fonts, so GitHub renders it without loading anything else.
"""

import os
from xml.sax.saxutils import escape

from common import path

W = 860
PAD = 24
SANS = "-apple-system,BlinkMacSystemFont,'Segoe UI',Inter,Helvetica,Arial,sans-serif"
MONO = "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace"

THEMES = {
    "dark": {
        "bg": "#07070D",
        "panel": "#0E0E1A",
        "grid": "#FFFFFF",
        "grid_op": "0.035",
        "border": "#262145",
        "text": "#ECEAFF",
        "muted": "#8B87B3",
        "a1": "#8B5CF6",
        "a2": "#22D3EE",
        "good": "#34D399",
        "warn": "#F59E0B",
    },
    "light": {
        "bg": "#FBFBFE",
        "panel": "#FFFFFF",
        "grid": "#1E1B4B",
        "grid_op": "0.05",
        "border": "#DDD8F3",
        "text": "#15122B",
        "muted": "#6A6690",
        "a1": "#7C3AED",
        "a2": "#0891B2",
        "good": "#059669",
        "warn": "#D97706",
    },
}


def n(x):
    return f"{x:,}"


def t(x, y, s, size=11, fill="text", font=MONO, weight=400, anchor="start", spacing=0, theme=None):
    return (
        f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" font-weight="{weight}" '
        f'fill="{theme[fill]}" text-anchor="{anchor}" letter-spacing="{spacing}">{escape(str(s))}</text>'
    )


def frame(h, theme, title, right):
    """Background, grid, border, corner brackets and the header bar."""
    c = theme
    b = 14  # bracket length
    corners = "".join(
        f'<path d="M{x0} {y0 + dy * b} V{y0} H{x0 + dx * b}" stroke="url(#acc)" stroke-width="2" fill="none"/>'
        for x0, y0, dx, dy in ((8, 8, 1, 1), (W - 8, 8, -1, 1), (8, h - 8, 1, -1), (W - 8, h - 8, -1, -1))
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{h}" viewBox="0 0 {W} {h}" role="img">
<defs>
  <linearGradient id="acc" x1="0" x2="1"><stop offset="0" stop-color="{c["a1"]}"/><stop offset="1" stop-color="{c["a2"]}"/></linearGradient>
  <linearGradient id="area" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="{c["a1"]}" stop-opacity="0.35"/><stop offset="1" stop-color="{c["a1"]}" stop-opacity="0"/></linearGradient>
  <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse"><path d="M24 0H0V24" fill="none" stroke="{c["grid"]}" stroke-opacity="{c["grid_op"]}"/></pattern>
</defs>
<rect width="{W}" height="{h}" rx="14" fill="{c["bg"]}"/>
<rect width="{W}" height="{h}" rx="14" fill="url(#grid)"/>
<rect x="0.5" y="0.5" width="{W - 1}" height="{h - 1}" rx="14" fill="none" stroke="{c["border"]}"/>
{corners}
<circle cx="{PAD + 5}" cy="31" r="4.5" fill="{c["good"]}"><animate attributeName="opacity" values="1;0.25;1" dur="2.4s" repeatCount="indefinite"/></circle>
{t(PAD + 18, 35, "ACCRETION", 13, weight=700, spacing=3, theme=c)}
{t(PAD + 128, 35, title, 12, "muted", spacing=1, theme=c)}
{t(W - PAD, 35, right, 11, "muted", anchor="end", theme=c)}
<rect x="{PAD}" y="50" width="{W - 2 * PAD}" height="1.5" fill="url(#acc)" opacity="0.8"/>
"""


def tile(x, y, w, h, label, value, sub, theme, big=True, value_fill="text"):
    c = theme
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{c["panel"]}" stroke="{c["border"]}"/>'
        + t(x + 14, y + 22, label.upper(), 10, "muted", spacing=1.5, theme=c)
        + t(x + 14, y + (56 if big else 47), value, 28 if big else 20, value_fill, SANS, 700, theme=c)
        + (t(x + 14, y + h - 12, sub, 10.5, "muted", theme=c) if sub else "")
    )


def category_bars(x, y, w, cats, theme):
    c = theme
    items = list(cats.items())
    top = items[:5]
    rest = sum(v for _, v in items[5:])
    if rest:
        top.append(("rest", rest))
    peak = max(v for _, v in top) or 1
    out = [t(x, y, "CATEGORIES", 10, "muted", spacing=1.5, theme=c)]
    bar_x, bar_w = x + 108, w - 108 - 56
    for i, (name, v) in enumerate(top):
        yy = y + 22 + i * 18
        out.append(t(x, yy, name, 11, theme=c))
        out.append(f'<rect x="{bar_x}" y="{yy - 9}" width="{bar_w}" height="8" rx="4" fill="{c["border"]}"/>')
        width = max(3, bar_w * v / peak)
        out.append(f'<rect x="{bar_x}" y="{yy - 9}" width="{width:.1f}" height="8" rx="4" fill="url(#acc)"/>')
        out.append(t(x + w, yy, n(v), 11, "muted", anchor="end", theme=c))
    return "".join(out)


def growth(x, y, w, h, m, history, theme):
    """Catalog growth by month from release dates; falls back to daily build history."""
    c = theme
    out = [t(x, y, "GROWTH", 10, "muted", spacing=1.5, theme=c)]
    top, bottom = y + 14, y + h - 30
    series = m.get("timeline") or [{"month": p["date"], "apps": p["apps"]} for p in history]
    pts = [p["apps"] for p in series]
    if len(pts) < 2:
        mid = (top + bottom) / 2
        out.append(
            f'<line x1="{x}" y1="{mid}" x2="{x + w}" y2="{mid}" stroke="{c["a1"]}" '
            f'stroke-dasharray="4 5" stroke-opacity="0.7"/>'
        )
        out.append(t(x, y + h, "collecting data", 10.5, "muted", theme=c))
        return "".join(out)
    lo, hi = min(pts), max(pts)
    span = (hi - lo) or 1
    step = w / (len(pts) - 1)
    coords = [(x + i * step, bottom - (p - lo) / span * (bottom - top - 6)) for i, p in enumerate(pts)]
    line = " ".join(f"{px:.1f},{py:.1f}" for px, py in coords)
    out.append(f'<polygon points="{x},{bottom} {line} {x + w},{bottom}" fill="url(#area)"/>')
    out.append(
        f'<polyline points="{line}" fill="none" stroke="url(#acc)" stroke-width="2" stroke-linejoin="round"/>'
    )
    lx, ly = coords[-1]
    out.append(f'<circle cx="{lx:.1f}" cy="{ly:.1f}" r="3.5" fill="{c["a2"]}"/>')
    out.append(t(x + w, y, f"{n(pts[-1])} apps", 10.5, "text", anchor="end", theme=c))
    out.append(t(x, bottom + 12, series[0]["month"], 9.5, "muted", theme=c))
    out.append(t(x + w, bottom + 12, "now", 9.5, "muted", anchor="end", theme=c))
    if "new_12m" in m:
        caption = f"+{n(m['new_12m'])} new apps in 12 months, +{n(m['new_30d'])} in 30 days"
    else:
        caption = f"+{n(pts[-1] - pts[0])} apps since {series[0]['month']}"
    out.append(t(x, y + h, caption, 10.5, "muted", theme=c))
    return "".join(out)


def stats_card(m, history, theme):
    h = 420
    c = theme
    gap = 12
    tw = (W - 2 * PAD - 3 * gap) / 4
    ratio = m["listings"] / m["apps"] if m["apps"] else 0
    down = m["sources_failed"]
    row1 = [
        ("apps", n(m["apps"]), "newest build of each"),
        ("sources", f"{m['sources']}/{m['sources_total']}", f"{m['sources_discovered']} auto-discovered"),
        ("listings scanned", n(m["listings"]), f"{ratio:.1f} listings per app"),
        ("duplicates resolved", n(m["duplicates"]), "apps found on 2+ sources"),
    ]
    row2 = [
        ("updated 7d", n(m["updated_7d"]), "good"),
        ("updated 30d", n(m["updated_30d"]), "text"),
        ("dead links purged", n(m["dead_links_removed"]), "text"),
        ("failed spec", n(m["rejected"]), "warn" if m["rejected"] else "text"),
    ]
    parts = [frame(h, c, "/ live index", f"build {m['updated']}")]
    for i, (label, value, sub) in enumerate(row1):
        parts.append(tile(PAD + i * (tw + gap), 66, tw, 96, label, value, sub, c))
    for i, (label, value, fill) in enumerate(row2):
        parts.append(
            tile(PAD + i * (tw + gap), 174, tw, 64, label, value, None, c, big=False, value_fill=fill)
        )
    half = (W - 2 * PAD - gap) / 2
    py = 252
    parts.append(
        f'<rect x="{PAD}" y="{py}" width="{half}" height="148" rx="9" fill="{c["panel"]}" stroke="{c["border"]}"/>'
    )
    parts.append(
        f'<rect x="{PAD + half + gap}" y="{py}" width="{half}" height="148" rx="9" '
        f'fill="{c["panel"]}" stroke="{c["border"]}"/>'
    )
    parts.append(category_bars(PAD + 14, py + 22, half - 28, m["categories"], c))
    gx = PAD + half + gap + 14
    parts.append(growth(gx, py + 22, half - 28, 90, m, history, c))
    status = "all sources up" if not down else f"{down} source{'s' if down > 1 else ''} down"
    footer = [
        f"core {n(m['curated_apps'])} apps / {m['curated_size_mb']} MB",
        f"full {m['size_mb']} MB",
        status,
    ]
    x = gx
    for line in footer:
        fill = "warn" if line == status and down else "muted"
        parts.append(t(x, py + 132, line, 10.5, fill, theme=c))
        x += len(line) * 6.4 + 18  # monospace at 10.5px is about 6.3px per character
    parts.append("</svg>")
    return "".join(parts)


def recent_card(m, theme):
    c = theme
    rows = m["recent"]
    h = 78 + len(rows) * 30 + 14
    parts = [frame(h, c, "/ latest builds", f"{n(m['updated_7d'])} apps updated this week")]
    for i, r in enumerate(rows):
        y = 84 + i * 30
        if i % 2 == 0:
            parts.append(
                f'<rect x="{PAD}" y="{y - 19}" width="{W - 2 * PAD}" height="28" rx="6" fill="{c["panel"]}"/>'
            )
        parts.append(t(PAD + 12, y, f"{i + 1:02d}", 11, "muted", theme=c))
        parts.append(t(PAD + 48, y, r["name"][:42], 13, "text", SANS, 600, theme=c))
        parts.append(t(W - PAD - 150, y, r["version"][:18], 12, "a1", anchor="end", theme=c))
        parts.append(t(W - PAD - 12, y, r["date"], 12, "muted", anchor="end", theme=c))
    parts.append("</svg>")
    return "".join(parts)


def render_cards(metrics, history):
    os.makedirs(path("assets"), exist_ok=True)
    for name, theme in THEMES.items():
        with open(path(f"assets/card-{name}.svg"), "w") as f:
            f.write(stats_card(metrics, history, theme))
        with open(path(f"assets/recent-{name}.svg"), "w") as f:
            f.write(recent_card(metrics, theme))
