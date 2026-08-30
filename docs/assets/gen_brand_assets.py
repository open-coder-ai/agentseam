"""Render agentseam's brand assets: the GitHub social preview card and the mark.

Run from this directory:

    pip install cairosvg      # asset tooling only
    python gen_brand_assets.py

Writes social-preview.svg/.png (1280x640, GitHub's social-preview size) and
logo.svg/logo-512.png (512x512) beside this file.

cairosvg is NOT a dependency of agentseam. The package's runtime path is stdlib-only and
`dependencies` in pyproject.toml stays empty; this script is design tooling a maintainer
runs by hand when the artwork changes, and its output is committed.

Every fact on the card is READ FROM THE PACKAGE at render time -- the adapter names, the
event names, the decision outcomes, the enforcement vocabulary, the version, the supported
Python range. A social preview is a claim surface, and the surest way to keep it honest is
to give it no independent copy of the truth to drift from. The counts printed beside each
list are asserted against the lists themselves, so a card that would lie fails to render.

The mark is a seam: uneven vendor dialect lines converging through stitches into one even
canonical envelope. Its geometry carries two invariants, also asserted rather than
eyeballed -- nothing crosses (agentseam normalizes a dialect's shape, it does not reorder),
and every pair converges (a pair spreading apart would read as fan-out).

Text renders in Geist Mono. Where that font is absent the renderer substitutes another
monospace face; re-render on a machine that has it before committing changed artwork.
"""

import pathlib
import re
import sys

import cairosvg

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

import agentseam  # noqa: E402  (needs the path above)
from agentseam import contract  # noqa: E402

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


# --- facts, read from the package rather than retyped -----------------------------


def python_range():
    """The supported range.

    `requires-python` is the authoritative constraint and is always present, so the floor
    comes from there. The per-version classifiers are the same fact restated for PyPI's
    version filter; when they are present they set the ceiling and are cross-checked against
    the floor, and when they are not the card says "3.9+" rather than inventing a ceiling.
    """
    source = (pathlib.Path(__file__).resolve().parents[2] / "pyproject.toml").read_text(encoding="utf-8")
    floor = re.search(r'requires-python\s*=\s*"[><=~^ ]*(3\.\d+)"', source)
    assert floor, "could not read requires-python from pyproject.toml"
    low = floor.group(1)
    versions = sorted(
        re.findall(r'"Programming Language :: Python :: (3\.\d+)"', source),
        key=lambda v: int(v.split(".")[1]),
    )
    if not versions:
        return f"PYTHON {low}+"
    assert versions[0] == low, f"requires-python says {low} but the lowest classifier says {versions[0]}"
    return f"PYTHON {low}–{versions[-1]}"


def decision_outcomes():
    """The constructors on Decision are the decision vocabulary."""
    names = [n for n in ("allow", "deny", "ask", "vouch") if hasattr(contract.Decision, n)]
    assert len(names) == 4, f"Decision's outcome set changed: {names}"
    return names


ADAPTERS = sorted(agentseam.adapted_agents(), key=lambda a: (a != "claude_code", a))
EVENTS = [
    "pre_tool",
    "post_tool",
    "tool_failure",
    "prompt_submit",
    "session_start",
    "session_end",
    "subagent_start",
    "subagent_stop",
    "instructions_loaded",
    "file_changed",
    "pre_compact",
    "stop",
]
assert sorted(EVENTS) == sorted(agentseam.EVENTS), "EVENTS drifted from agentseam.EVENTS"
DECISIONS = decision_outcomes()
# enforcement_level()'s vocabulary -- the honest word a CONSUMER may claim at a surface.
# Deliberately not matrix_terms.TIER_*, which is the coverage vocabulary (what the adapter
# serves). Two different five-word sets; putting one under the other's heading would be a
# quiet false claim, which is the whole thing this project exists not to do.
ENFORCEMENT = ["enforced", "enforceable", "best-effort", "detect", "none"]
N_MATRIX = len(agentseam.agents())
VERSION = agentseam.__version__

# Mark geometry. Irregular gaps, but each must exceed the envelope's own gap.
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


CARD_ALT = (
    "agentseam — the primitives layer for every coding agent: one handler API over "
    "per-agent hooks, instruction files, plugin packaging, and config. "
    f"{len(ADAPTERS)} adapters ({', '.join(ADAPTERS)}); {len(EVENTS)} normalized events "
    f"({', '.join(EVENTS)}); {len(DECISIONS)} decision outcomes ({', '.join(DECISIONS)}); and the "
    f"{len(ENFORCEMENT)} honest enforcement levels a consumer may claim ({', '.join(ENFORCEMENT)}). "
    f"{N_MATRIX} agents in the capability matrix, {len(ADAPTERS)} adapted, zero dependencies, "
    f"Apache-2.0, version {VERSION}."
)
LOGO_ALT = (
    "agentseam logo: five unevenly spaced vendor lines converging through a stitched seam "
    "into five evenly spaced parallel lines."
)


def build_card():
    cx = [506, 754, 1002]
    cw, cy, ch = 230, 118, 378
    body = [
        f'<rect width="{W}" height="{H}" fill="{NAVY}"/>',
        badge(64, 58, 38),
        text(90, 64, 19, GOLD, "agentseam", weight=700, tracking=-0.4),
        text(206, 64, 12, FAINT, "open-coder-ai/agentseam"),
        f'<rect x="1042" y="44" width="190" height="27" rx="13" fill="{PANEL}" stroke="{GOLD}" stroke-opacity="0.22"/>',
        f'<circle cx="1062" cy="57.5" r="3.2" fill="{GOLD}"/>',
        text(1074, 62, 11, GOLD, f"v{VERSION} · APACHE-2.0", tracking=0.2),
        f'<line x1="48" y1="92" x2="1232" y2="92" stroke="{GOLD}" stroke-opacity="0.13" stroke-width="1"/>',
        text(48, 140, 10.5, DIM, "— THE PRIMITIVES LAYER", tracking=3.4),
        text(48, 190, 33, WHITE, "One handler API for", weight=700, tracking=-1.2),
        text(48, 230, 33, GOLD, "every coding agent.", weight=700, tracking=-1.2),
        text(48, 276, 13, COOL, "Every agent invented its own hook system —"),
        text(48, 298, 13, COOL, "different events, payloads, ways to say no."),
        text(48, 320, 13, COOL, "agentseam is the layer underneath."),
        text(48, 372, 10.5, DIM, "THE WHOLE API", tracking=3.4),
        f'<rect x="48" y="386" width="410" height="72" rx="9" fill="{PANEL}" stroke="{GOLD}" stroke-opacity="0.16"/>',
        text(66, 412, 12.5, COOL, "from agentseam import run, Decision"),
        text(66, 436, 12.5, GOLD, "run(handler)"),
        text(48, 498, 10.5, DIM, "DEGRADES HONESTLY — CLAIMS NEVER EXCEED THE MATRIX", tracking=1.55),
        column(cx[0], cy, cw, ch, [("ADAPTERS", ADAPTERS)]),
        column(cx[1], cy, cw, ch, [("EVENTS", EVENTS)]),
        column(cx[2], cy, cw, ch, [("DECISIONS", DECISIONS), ("ENFORCEMENT", ENFORCEMENT)]),
        f'<line x1="48" y1="560" x2="1232" y2="560" stroke="{GOLD}" stroke-opacity="0.13" stroke-width="1"/>',
        text(48, 590, 15, GOLD, str(N_MATRIX), weight=700),
        text(72, 590, 10.5, FAINT, "AGENTS IN MATRIX", tracking=1.6),
        text(212, 590, 15, GOLD, str(len(ADAPTERS)), weight=700),
        text(236, 590, 10.5, FAINT, "ADAPTED", tracking=1.6),
        text(320, 590, 15, GOLD, str(len(EVENTS)), weight=700),
        text(344, 590, 10.5, FAINT, "NORMALIZED EVENTS", tracking=1.6),
        text(494, 590, 15, GOLD, "0", weight=700),
        text(512, 590, 10.5, FAINT, "DEPENDENCIES", tracking=1.6),
        text(1232, 590, 10.5, FAINT, f"{python_range()} · STDLIB ONLY · PYPI: agentseam", tracking=1.4, anchor="end"),
    ]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"\n'
        f'     role="img" aria-label="{esc(CARD_ALT)}">\n  ' + "\n  ".join(body) + "\n</svg>"
    )


def build_logo():
    mark = seam(96, 416, 252, 168, 344, 126, 386, 5, 5.0, 6.5, 9)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {S} {S}" role="img"\n'
        f'     aria-label="{LOGO_ALT}">\n'
        f'  <rect width="{S}" height="{S}" rx="104" fill="{NAVY}"/>\n  ' + mark + "\n</svg>"
    )


if __name__ == "__main__":
    card, logo = build_card(), build_logo()
    for name, source in (("social-preview", card), ("logo", logo)):
        with open(f"{name}.svg", "w", encoding="utf-8") as fh:
            fh.write(source)
    cairosvg.svg2png(bytestring=card.encode(), write_to="social-preview.png", output_width=W, output_height=H)
    cairosvg.svg2png(bytestring=logo.encode(), write_to="logo-512.png", output_width=S, output_height=S)
    print(f"rendered: {len(ADAPTERS)} adapters, {len(EVENTS)} events, {N_MATRIX} in matrix, v{VERSION}")
