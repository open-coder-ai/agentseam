"""The per-agent enforcement table, derived from the matrix instead of kept in step by hand.

Owner decision, 2026-09-13: if the seam owns vendor conformance, the enforcement table is
its output rather than a thing maintained by hand in each consumer's instructions. A
hand-written copy drifts silently and in the direction that flatters: nobody notices a
table still claiming last month's tier, and a table is exactly where a reader goes to
avoid reading the code.

What this module will NOT emit is the consumer's own column. `T3`, `hook + CI`, `CI only`
are chock's vocabulary for how chock wires a control; agentseam does not know them and must
not learn them. It emits the columns it owns -- tier, grade, fail mode, basis, date -- and a
consumer joins its wiring column onto them. Rendering a chock tier here would put
chock-family knowledge in the engine, which is the one thing this package may never carry.

The grade column is the load-bearing one, and it is the reason a derived table is worth the
work rather than a tidy-up: it is capped by basis, so a row resting on vendor docs cannot
print `enforced` however confident its cell reads. A hand-written table has no such
mechanism, and every hand-written copy of this table checked so far over-claimed somewhere.
"""

from __future__ import annotations

from .contract import PRE_TOOL
from .matrix import MATRIX, basis, enforcement_level
from .matrix_terms import TIER_NONE, TIER_UNADAPTED

#: The columns agentseam owns. A consumer's wiring column is appended by the consumer.
COLUMNS = ("agent", "tier", "grade", "fail_mode", "basis", "recorded")

#: What a row prints where the vendor offers no hook surface at all. Not "fail-open": there
#: is nothing to fail. Saying `n/a` keeps the absence visible instead of dressing it as a
#: weak capability.
NOT_APPLICABLE = "n/a"


def rows(event=PRE_TOOL):
    """One dict per agent: what it can enforce at `event` and what that claim rests on."""
    out = []
    for agent in sorted(MATRIX):
        row = MATRIX[agent]
        cap = row["events"].get(event)
        out.append(
            {
                "agent": agent,
                "tier": row["tier"],
                "grade": enforcement_level(agent, event),
                "fail_mode": cap["fail_mode"] if cap else NOT_APPLICABLE,
                "basis": basis(agent) or NOT_APPLICABLE,
                "recorded": row["verified"].get("date") or NOT_APPLICABLE,
            }
        )
    return out


def unadapted():
    """Agents with no hook surface, which a consumer can only reach by instruction files."""
    return sorted(a for a, row in MATRIX.items() if row["tier"] in (TIER_NONE, TIER_UNADAPTED))


def markdown(event=PRE_TOOL, *, columns=COLUMNS):
    """The table as GitHub-flavoured markdown, ready to paste into a consumer's instructions."""
    missing = [c for c in columns if c not in COLUMNS]
    if missing:
        raise ValueError("not columns this table owns: %s -- own columns are %s" % (missing, list(COLUMNS)))
    lines = [
        "| %s |" % " | ".join(_heading(c) for c in columns),
        "|%s|" % "|".join("---" for _ in columns),
    ]
    for row in rows(event):
        lines.append("| %s |" % " | ".join(str(row[c]) for c in columns))
    return "\n".join(lines)


def _heading(column):
    return column.replace("_", " ").capitalize()
