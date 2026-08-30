"""Render agentseam's brand assets: the GitHub social preview card and the mark.

Run from this directory:

    pip install cairosvg      # asset tooling only
    python gen_brand_assets.py

Writes social-preview.svg/.png (1280x640, GitHub's social-preview size) and
logo.svg/logo-512.png (512x512) beside this file.

cairosvg is NOT a dependency of agentseam. The package's runtime path is stdlib-only and
`dependencies` in pyproject.toml stays empty; this script is design tooling a maintainer
runs by hand when the artwork changes, and its output is committed.

The figure states the project's claim, so it has to be true to it. Two invariants, both
enforced by the gap tables below and asserted at render time:

  * Nothing crosses. agentseam normalizes the *shape* of a vendor's hook dialect; it does
    not reorder anything. Crossing lines would say otherwise.
  * Every pair converges: each gap on the dialect side is wider than the matching gap on
    the envelope side. A pair that spread apart would read as fan-out, the opposite of
    what the layer does.

Text renders in Geist Mono, matching the sibling project's cards. Where that font is
absent the renderer substitutes another monospace face; re-render on a machine that has
it before committing a changed card.
"""

import cairosvg

NAVY = "#0D1626"
GOLD = "#D9B45C"
DIM = "#8A7340"
COOL = "#9FB0C4"
FONT = "Geist Mono"

# Card: 12 dialect lines, one per adapter in src/agentseam/adapters/. Irregular gaps
# (heterogeneous vendor surfaces), but every one exceeds the envelope's 30.5px gap.
GAPS = [0, 32, 45, 34, 47, 33, 43, 36, 46, 35, 41, 40]
# Ragged left edge: the dialects do not start from a tidy margin either.
RAG = [0, 34, 12, 46, 6, 28, 18, 52, 10, 38, 22, 44]
# The mark carries only five lines, so its minimum gap has to clear a wider 44px envelope.
LOGO_GAPS = [0, 1.76, 1.00, 1.36, 1.08]


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


def seam(
    x0,
    x1,
    sx,
    ytop,
    ybot,
    ly0,
    ly1,
    n,
    swl,
    swr,
    node,
    cap=None,
    cap_y=None,
    cap_size=11,
    opl=0.36,
    stub=3.0,
    rag=1.0,
    gaps=None,
):
    """Uneven dialect lines on the left, a stitched seam at sx, an even envelope right."""
    ry = spread(ytop, ybot, [1] * n)  # ordered, even: the canonical envelope
    ly = spread(ly0, ly1, (gaps or GAPS)[:n])  # uneven, wider: the vendor dialects
    check_invariants(ly, ry)
    parts = []
    for i in range(n):
        parts.append(
            f'<line x1="{x0 + RAG[i % len(RAG)] * rag:.1f}" y1="{ly[i]:.1f}" '
            f'x2="{sx:.1f}" y2="{ry[i]:.1f}" stroke="{GOLD}" stroke-width="{swl}" '
            f'stroke-opacity="{opl}" stroke-linecap="round"/>'
        )
    for i in range(n):
        parts.append(
            f'<line x1="{sx:.1f}" y1="{ry[i]:.1f}" x2="{x1:.1f}" y2="{ry[i]:.1f}" '
            f'stroke="{GOLD}" stroke-width="{swr}" stroke-opacity="0.95" stroke-linecap="round"/>'
        )
    # The seam itself: one continuous join, not a line broken by the stitches.
    parts.append(
        f'<line x1="{sx:.1f}" y1="{ytop - node * stub:.1f}" x2="{sx:.1f}" '
        f'y2="{ybot + node * stub:.1f}" stroke="{GOLD}" stroke-width="{swr}" stroke-opacity="0.42"/>'
    )
    # Each crossing is a stitch: a node where the two planes are held together.
    for i in range(n):
        parts.append(
            f'<rect x="{sx - node:.1f}" y="{ry[i] - node:.1f}" width="{node * 2:.1f}" '
            f'height="{node * 2:.1f}" transform="rotate(45 {sx:.1f} {ry[i]:.1f})" fill="{GOLD}"/>'
        )
    if cap:
        parts.append(
            f'<text x="{(x0 + x1) / 2:.1f}" y="{cap_y}" font-family="{FONT}" '
            f'font-size="{cap_size}" letter-spacing="3.6" fill="{DIM}" text-anchor="middle">{cap}</text>'
        )
    return "\n  ".join(parts)


def corners(w, h, m=44, length=16, sw=1.4):
    return "\n  ".join(
        f'<path d="M {x + dx * length} {y} L {x} {y} L {x} {y + dy * length}" fill="none" '
        f'stroke="{GOLD}" stroke-opacity="0.30" stroke-width="{sw}"/>'
        for (x, y, dx, dy) in ((m, m, 1, 1), (w - m, m, -1, 1), (m, h - m, 1, -1), (w - m, h - m, -1, -1))
    )


W, H = 1280, 640
S = 512
CARD_ALT = (
    "agentseam — the primitives layer for every coding agent: one handler API over "
    "per-agent hooks, instruction files, plugin packaging, and config. Twelve unevenly "
    "spaced vendor hook dialects converge through a stitched seam into one evenly spaced "
    "canonical envelope."
)
LOGO_ALT = (
    "agentseam logo: five unevenly spaced vendor lines converging through a stitched seam "
    "into five evenly spaced parallel lines."
)


def text(x, y, size, fill, body, weight=None, tracking=None):
    attrs = [f'x="{x}"', f'y="{y}"', f'font-family="{FONT}"', f'font-size="{size}"']
    if weight:
        attrs.append(f'font-weight="{weight}"')
    if tracking is not None:
        attrs.append(f'letter-spacing="{tracking}"')
    attrs.append(f'fill="{fill}"')
    return "<text " + " ".join(attrs) + f">{body}</text>"


def build_card():
    body = [
        f'<rect width="{W}" height="{H}" fill="{NAVY}"/>',
        corners(W, H),
        text(88, 236, 13, DIM, "PRIMITIVES LAYER", tracking=5.2),
        text(84, 322, 78, GOLD, "agentseam", weight=700, tracking=-1.5),
        f'<line x1="88" y1="356" x2="566" y2="356" stroke="{GOLD}" stroke-opacity="0.28" stroke-width="1.2"/>',
        text(88, 398, 19, COOL, "One handler API over per-agent hooks,"),
        text(88, 426, 19, COOL, "instruction files, plugin packaging, config."),
        text(88, 524, 12, DIM, "12 ADAPTERS &#183; STDLIB-ONLY &#183; APACHE-2.0", tracking=3.4),
        seam(
            664,
            1192,
            930,
            152,
            488,
            104,
            536,
            12,
            1.6,
            2.0,
            4.2,
            cap="VENDOR DIALECTS &#8594; CANONICAL ENVELOPE",
            cap_y=576,
        ),
    ]
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}"\n'
        f'     role="img" aria-label="{CARD_ALT}">\n  ' + "\n  ".join(body) + "\n</svg>"
    )


def build_logo():
    mark = seam(
        96,
        416,
        252,
        168,
        344,
        126,
        386,
        5,
        5.0,
        6.5,
        9,
        opl=0.52,
        stub=1.8,
        rag=0.55,
        gaps=LOGO_GAPS,
    )
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
    print("rendered social-preview.svg/.png and logo.svg/logo-512.png")
