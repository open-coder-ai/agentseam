"""Shared drawing primitives for agentseam's brand assets.

Split out of gen_brand_assets.py to stay inside the 300-line review budget AGENTS.md sets,
whose stated remedy is split_by_activity. This file is the drawing language -- palette,
text, the seam figure, panels, the card layout, and the drift check. gen_brand_assets.py is
what agentseam has to say. Two activities, two files.

Nothing here knows anything about agentseam: it takes lists and labels and returns SVG. The
assertions are the point -- a figure whose lines cross or diverge, or a row too long for its
panel, raises rather than rendering something that quietly contradicts the project it
illustrates.
"""

import pathlib
import re

NAVY = "#0D1626"
PANEL = "#111E33"
GOLD = "#D9B45C"
DIM = "#8A7340"
COOL = "#9FB0C4"
FAINT = "#5A6B80"
WHITE = "#E8EEF6"
FONT = "Geist Mono"
W, H = 1280, 640
S = 512

LOGO_GAPS = [0, 1.76, 1.00, 1.36, 1.08]


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, size, fill, body, weight=None, tracking=None, anchor=None, opacity=None):
    attrs = [f'x="{x}"', f'y="{y}"', f'font-family="{FONT}"', f'font-size="{size}"']
    if weight:
        attrs.append(f'font-weight="{weight}"')
    if tracking is not None:
        attrs.append(f'letter-spacing="{tracking}"')
    if anchor:
        attrs.append(f'text-anchor="{anchor}"')
    attrs.append(f'fill="{fill}"')
    if opacity is not None:
        attrs.append(f'fill-opacity="{opacity}"')
    return "<text " + " ".join(attrs) + f">{esc(body)}</text>"


def spread(y0, y1, gaps):
    """n points from y0 to y1 inclusive; gaps[1:] are the n-1 intervals between them."""
    intervals = gaps[1:]
    total = sum(intervals)
    out = [float(y0)]
    acc = 0.0
    for gap in intervals:
        acc += gap
        out.append(y0 + (y1 - y0) * (acc / total))
    return out


def check_invariants(left, right):
    """Fail loudly rather than ship a figure that contradicts the claim it illustrates."""
    lg = [left[i + 1] - left[i] for i in range(len(left) - 1)]
    rg = [right[i + 1] - right[i] for i in range(len(right) - 1)]
    assert all(g > 0 for g in lg + rg), "lines cross: agentseam does not reorder"
    assert all(a > b for a, b in zip(lg, rg)), "a pair diverges: the figure must converge"


def seam(x0, x1, sx, ytop, ybot, ly0, ly1, n, swl, swr, node, opl=0.52, stub=1.8, rag=0.55, gaps=None, ragged=None):
    ry = spread(ytop, ybot, [1] * n)
    ly = spread(ly0, ly1, (gaps or LOGO_GAPS)[:n])
    check_invariants(ly, ry)
    ragged = ragged or [0, 34, 12, 46, 6]
    parts = []
    for i in range(n):
        parts.append(
            f'<line x1="{x0 + ragged[i % len(ragged)] * rag:.1f}" y1="{ly[i]:.1f}" '
            f'x2="{sx:.1f}" y2="{ry[i]:.1f}" stroke="{GOLD}" stroke-width="{swl}" '
            f'stroke-opacity="{opl}" stroke-linecap="round"/>'
        )
        parts.append(
            f'<line x1="{sx:.1f}" y1="{ry[i]:.1f}" x2="{x1:.1f}" y2="{ry[i]:.1f}" '
            f'stroke="{GOLD}" stroke-width="{swr}" stroke-opacity="0.95" stroke-linecap="round"/>'
        )
    parts.append(
        f'<line x1="{sx:.1f}" y1="{ytop - node * stub:.1f}" x2="{sx:.1f}" '
        f'y2="{ybot + node * stub:.1f}" stroke="{GOLD}" stroke-width="{swr}" stroke-opacity="0.42"/>'
    )
    for y in ry:
        parts.append(
            f'<rect x="{sx - node:.1f}" y="{y - node:.1f}" width="{node * 2:.1f}" '
            f'height="{node * 2:.1f}" transform="rotate(45 {sx:.1f} {y:.1f})" fill="{GOLD}"/>'
        )
    return "\n  ".join(parts)


def badge(cx, cy, size):
    """The mark at header scale: three lines, so it stays legible small."""
    parts = [
        f'<rect x="{cx - size / 2:.1f}" y="{cy - size / 2:.1f}" width="{size}" height="{size}" '
        f'rx="{size * 0.22:.1f}" fill="{PANEL}"/>'
    ]
    parts.append(
        seam(
            cx - size * 0.34,
            cx + size * 0.34,
            cx,
            cy - size * 0.20,
            cy + size * 0.20,
            cy - size * 0.33,
            cy + size * 0.33,
            3,
            size * 0.035,
            size * 0.045,
            size * 0.055,
            opl=0.55,
            stub=1.1,
            rag=0.10,
            gaps=[0, 1.9, 1.15],
            ragged=[0, 34, 12],
        )
    )
    return "\n  ".join(parts)


def column(x, y, w, h, groups):
    """One bordered panel holding one or more labelled lists."""
    parts = [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{PANEL}" '
        f'stroke="{GOLD}" stroke-opacity="0.16" stroke-width="1"/>'
    ]
    pad = 17
    cy = y + 29
    for index, (label, rows) in enumerate(groups):
        if index:
            cy += 20
        parts.append(f'<circle cx="{x + pad + 3}" cy="{cy - 4}" r="2.6" fill="{GOLD}" fill-opacity="0.9"/>')
        parts.append(text(x + pad + 13, cy, 11, GOLD, label, weight=700, tracking=2.3))
        parts.append(text(x + w - pad, cy, 14, GOLD, str(len(rows)), weight=700, anchor="end"))
        cy += 11
        parts.append(
            f'<line x1="{x + pad}" y1="{cy}" x2="{x + w - pad}" y2="{cy}" stroke="{GOLD}" '
            f'stroke-opacity="0.14" stroke-width="1" stroke-dasharray="2 3"/>'
        )
        cy += 21
        for i, row in enumerate(rows):
            parts.append(f'<circle cx="{x + pad + 3}" cy="{cy - 4}" r="1.7" fill="{COOL}" fill-opacity="0.5"/>')
            parts.append(text(x + pad + 13, cy, 12.5, WHITE if i == 0 else COOL, row))
            cy += 26
    return "\n  ".join(parts)


def check(svg, stem):
    """Compare a freshly derived asset against the committed one; report what drifted.

    The committed image is a snapshot of facts that live in the package, so adding an
    adapter or an event silently invalidates it. Nothing here is hand-typed -- every count
    is len() of a list read at render time -- but a stale image is wrong all the same, and
    it is what a link preview shows to someone who has not read the repo yet.

    The comparison is on the SVG, never the PNG: the SVG is plain text derived only from
    repository data, so it is byte-identical on any machine, while a PNG depends on the
    font installed on the renderer. Any drift in the facts reaches the SVG first.
    """
    path = pathlib.Path(f"{stem}.svg")
    if not path.exists():
        return [f"{path} is missing"]
    committed = path.read_text(encoding="utf-8")
    if committed == svg:
        return []
    fresh = re.findall(r">([^<>]+)</text>", svg)
    old = re.findall(r">([^<>]+)</text>", committed)
    added = [r for r in fresh if r not in old]
    removed = [r for r in old if r not in fresh]
    detail = []
    if added:
        detail.append("  now present: " + ", ".join(added[:8]) + (" …" if len(added) > 8 else ""))
    if removed:
        detail.append("  no longer:   " + ", ".join(removed[:8]) + (" …" if len(removed) > 8 else ""))
    return [f"{path} is out of date"] + detail
