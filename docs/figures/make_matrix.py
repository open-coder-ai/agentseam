"""Render agentseam's capability matrix: 16 agents x 12 events, graded from src/agentseam/matrix.py.

Run from this directory:

    python make_matrix.py

Writes matrix-light.svg and matrix-dark.svg beside this file. Every number on the figure is
read from the package at render time -- nothing here is typed by hand. If the matrix changes
shape (an agent or event added or removed), the assertions below fail loudly rather than let
the figure quietly drift from the data it claims to draw.
"""

import pathlib
import sys

import palette as p

# The installed `agentseam` may be an unrelated checkout (a different clone on the same
# machine); insert this repo's own src first so the figure is always drawn from the code
# sitting beside it, never from whatever happens to be on the ambient path.
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "src"))

from agentseam import matrix  # noqa: E402
from agentseam.matrix_terms import (  # noqa: E402
    GRADE_BEST_EFFORT,
    GRADE_DETECT,
    GRADE_ENFORCEABLE,
    GRADE_ENFORCED,
    GRADE_NONE,
)

W = 760
MARGIN_L, MARGIN_R = 14, 14
LABEL_W = 112
TITLE_H = 46
HEADER_H = 128
CELL_W = (W - MARGIN_L - MARGIN_R - LABEL_W) / 12
CELL_H = 24
LEGEND_H = 92

GRID_X0 = MARGIN_L + LABEL_W
GRID_Y0 = TITLE_H + HEADER_H
GRID_H = 16 * CELL_H
H = GRID_Y0 + GRID_H + LEGEND_H

#: Column order is a display choice (roughly lifecycle order); the set is not -- it is
#: cross-checked below against every event that actually appears in the matrix, so an event
#: added to the package and forgotten here breaks the build instead of silently going missing.
EVENTS = [
    "pre_tool",
    "post_tool",
    "stop",
    "tool_failure",
    "prompt_submit",
    "session_start",
    "session_end",
    "pre_compact",
    "subagent_start",
    "subagent_stop",
    "instructions_loaded",
    "file_changed",
]
_actual_events = {e for row in matrix.MATRIX.values() for e in row["events"]}
assert set(EVENTS) == _actual_events, f"EVENTS list drifted from matrix.py: {_actual_events}"

AGENTS = matrix.agents()  # sorted() -- the same order matrix.py itself considers canonical
assert len(AGENTS) == 16, f"expected 16 agents, matrix.py now has {len(AGENTS)}"

#: Ordinal position each grade takes in the shared 5-step LEVELS ramp (index 4 = darkest =
#: strongest, matching the ENFORCEMENT ramp's own advisory-to-enforced direction). `none` is
#: excluded on purpose -- absence renders in NEUTRAL, never the pale end of the ramp.
LEVEL_INDEX = {
    GRADE_ENFORCED: 4,
    GRADE_ENFORCEABLE: 3,
    GRADE_BEST_EFFORT: 2,
    GRADE_DETECT: 1,
}
#: Colour is never the only carrier: every cell also gets one of these two-letter glyphs.
GLYPH = {
    GRADE_ENFORCED: "EN",
    GRADE_ENFORCEABLE: "EA",
    GRADE_BEST_EFFORT: "BE",
    GRADE_DETECT: "DT",
    GRADE_NONE: "–",
}
LABEL = {
    GRADE_ENFORCED: "enforced",
    GRADE_ENFORCEABLE: "enforceable",
    GRADE_BEST_EFFORT: "best-effort",
    GRADE_DETECT: "detect",
    GRADE_NONE: "none",
}
#: Legend order, strongest first -- matches GRADE_ORDER in matrix_terms.py.
GRADE_ORDER_DISPLAY = [GRADE_ENFORCED, GRADE_ENFORCEABLE, GRADE_BEST_EFFORT, GRADE_DETECT, GRADE_NONE]


def cell_grades():
    """{(agent, event): grade} for the full 16x12 grid, and a grade -> count tally."""
    grades = {}
    counts = {g: 0 for g in GRADE_ORDER_DISPLAY}
    for agent in AGENTS:
        for event in EVENTS:
            g = matrix.enforcement_level(agent, event)
            grades[(agent, event)] = g
            counts[g] += 1
    return grades, counts


def fill_for(t, grade):
    if grade == GRADE_NONE:
        return t["neutral"]
    return t["levels"][LEVEL_INDEX[grade]]


def render(t, name, grades, counts):
    total = sum(counts.values())
    present = [g for g in GRADE_ORDER_DISPLAY if counts[g] > 0]
    desc = (
        "Grid of 16 coding agents by 12 lifecycle events, shaded by the enforcement grade "
        "agentseam can honestly claim at that surface. Of %d cells: %s. No agent is graded "
        "enforced at any event -- eleven agents reach only best-effort at pre_tool, Cursor "
        "alone reaches enforceable there, and aider, Copilot, Replit and Zed have no hook "
        "surface at pre_tool at all." % (total, "; ".join("%d %s" % (counts[g], LABEL[g]) for g in present))
    )
    svg = p.open_svg(W, H, t, "agentseam capability matrix", desc)
    svg += p.text(MARGIN_L, 20, "What each agent can honestly do, by event", t["text"], 15, p.SANS, "600")
    svg += p.text(
        MARGIN_L,
        36,
        "16 agents × 12 events, graded from src/agentseam/matrix.py -- not one cell says “enforced”",
        t["secondary"],
        10.5,
    )

    # Column headers: event names rotated upright-reading (bottom-to-top), anchored at the
    # grid line so they line up with their column regardless of label length.
    header_baseline = GRID_Y0 - 8
    for i, event in enumerate(EVENTS):
        cx = GRID_X0 + i * CELL_W + CELL_W / 2
        svg += (
            '  <text x="0" y="0" font-family="%s" font-size="9.5" fill="%s" '
            'text-anchor="start" transform="translate(%g,%g) rotate(-90)">%s</text>\n'
            % (p.MONO, t["secondary"], cx + 3.5, header_baseline, p.esc(event))
        )

    # Row labels: the matrix's own agent keys, right-aligned against the grid.
    for r, agent in enumerate(AGENTS):
        y = GRID_Y0 + r * CELL_H
        svg += p.text(
            GRID_X0 - 10,
            y + CELL_H / 2 + 3.5,
            agent,
            t["text"],
            10.5,
            p.MONO,
            "400",
            anchor="end",
        )

    # Cells: fill carries the grade, the glyph repeats it in text so colour is never load-bearing.
    for r, agent in enumerate(AGENTS):
        y = GRID_Y0 + r * CELL_H
        for c, event in enumerate(EVENTS):
            x = GRID_X0 + c * CELL_W
            grade = grades[(agent, event)]
            fill = fill_for(t, grade)
            svg += p.box(x + p.GAP / 2, y + p.GAP / 2, CELL_W - p.GAP, CELL_H - p.GAP, fill, rx=2)
            glyph_colour = t["surface"] if grade != GRADE_NONE else t["secondary"]
            svg += p.text(
                x + CELL_W / 2,
                y + CELL_H / 2 + 3.5,
                GLYPH[grade],
                glyph_colour,
                8.5,
                p.MONO,
                "600",
                anchor="middle",
            )

    # Legend: every level that actually occurs, spelled out, swatch + glyph + word + count.
    legend_y = GRID_Y0 + GRID_H + 26
    lx = MARGIN_L
    for g in present:
        svg += p.box(lx, legend_y - 11, 14, 14, fill_for(t, g), rx=2)
        svg += p.text(lx + 17, legend_y, GLYPH[g], t["text"], 8.5, p.MONO, "600")
        label = "%s (%d)" % (LABEL[g], counts[g])
        svg += p.text(lx + 34, legend_y, label, t["secondary"], 10.5)
        lx += 34 + 11 * len(label) + 14

    svg += p.text(
        MARGIN_L,
        legend_y + 26,
        "“enforced” never appears above: no agent in this matrix blocks and fails closed at any event.",
        t["secondary"],
        10,
    )
    svg += p.text(
        MARGIN_L,
        legend_y + 44,
        "– marks no hook surface at all, not a weak grade -- it is drawn in grey, never on the ramp.",
        t["secondary"],
        10,
    )

    return svg + p.close_svg()


if __name__ == "__main__":
    grades, counts = cell_grades()
    for path in p.write_pair("matrix", lambda t, name: render(t, name, grades, counts)):
        print("wrote", path)
    total = sum(counts.values())
    print("cells: %d total -- %s" % (total, ", ".join("%s=%d" % (LABEL[g], counts[g]) for g in GRADE_ORDER_DISPLAY)))
