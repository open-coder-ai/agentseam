"""Render agentseam's GitHub social-preview card: name, one line, one real number.

Run from this directory:

    python make_social.py

Writes social-card.svg (1280x640, light only -- GitHub's social preview has no dark variant)
and, when cairosvg is importable, social-card.png beside it. The SVG is the source of truth
and is stdlib-only; the CI drift job that regenerates every docs/figures/make_*.py script does
not install cairosvg, so PNG rendering degrades to a skip with a printed note there rather than
failing the job -- a maintainer with cairosvg installed regenerates and commits the PNG by hand
when the SVG's facts change, the same split docs/assets/gen_brand_assets.py already draws
between "facts reach the SVG first" and a PNG that depends on the renderer's fonts.

The one number is pulled from make_matrix's own tally rather than recomputed, so the two
figures can never quote different counts for the same run.
"""

import pathlib

import palette as p
from make_matrix import cell_grades  # also puts this repo's src first on sys.path

from agentseam.matrix_terms import GRADE_ENFORCED  # noqa: E402

W, H = 1280, 640


def build():
    t = p.theme("light")
    _grades, counts = cell_grades()
    total = sum(counts.values())
    enforced = counts[GRADE_ENFORCED]

    desc = (
        "agentseam: one handler API over every coding agent's hooks, instruction files, "
        "plugin packaging and config. %d of %d capability-matrix cells are graded enforced." % (enforced, total)
    )
    svg = p.open_svg(W, H, t, "agentseam", desc)

    svg += p.text(72, 296, "agentseam", t["text"], 72, p.MONO, "700")
    svg += p.text(
        74,
        344,
        "one handler API over every coding agent's hooks — graded, not assumed",
        t["secondary"],
        24,
    )

    # The headline number, in the card's one true fact: how many cells are graded enforced.
    # Drawn in NEUTRAL, the same colour absence takes in the matrix figure itself, so a
    # reader who has seen that figure recognizes the tie rather than reading a new colour.
    svg += p.box(74, 436, 30, 30, t["neutral"], rx=3)
    svg += p.text(74 + 15, 436 + 21, "–", t["secondary"], 15, p.MONO, "600", anchor="middle")
    svg += p.text(
        118,
        460,
        "%d of %d capability-matrix cells graded enforced" % (enforced, total),
        t["text"],
        26,
        p.SANS,
        "600",
    )
    svg += p.text(
        74,
        500,
        "16 agents × 12 events, verified from src/agentseam/matrix.py — not one cell claims more than its evidence.",
        t["secondary"],
        15,
    )
    svg += p.box(0, H - 8, W, 8, t["enforcement"][1], rx=0)

    return svg + p.close_svg()


if __name__ == "__main__":
    svg = build()
    out_dir = pathlib.Path(__file__).resolve().parent
    (out_dir / "social-card.svg").write_text(svg, encoding="utf-8", newline="\n")
    print("wrote", out_dir / "social-card.svg")

    try:
        import cairosvg
    except ImportError:
        print("cairosvg not installed -- skipping social-card.png (SVG is the source of truth)")
    else:
        cairosvg.svg2png(bytestring=svg.encode(), write_to=str(out_dir / "social-card.png"), output_width=W)
        print("wrote", out_dir / "social-card.png")
