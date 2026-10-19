"""llms.txt's matrix tallies are recounted from the matrix, so they cannot drift."""

import re
from collections import Counter
from pathlib import Path

from agentseam.contract import EVENTS
from agentseam.matrix import MATRIX, basis, enforcement_level

LLMS = (Path(__file__).resolve().parents[1] / "llms.txt").read_text(encoding="utf-8")
LEVELS = ("none", "detect", "best-effort", "enforceable", "enforced")
_PROSE = " ".join(LLMS.split())


def test_the_cell_tally_matches_the_matrix():
    m = re.search(r"covers (\d+) agents by (\d+) events: (\d+) cells, of which (.*?)\.", _PROSE)
    assert m, "llms.txt lost its cell tally"
    assert [int(g) for g in m.groups()[:3]] == [len(MATRIX), len(EVENTS), len(MATRIX) * len(EVENTS)]
    stated = {lvl: int(n) for n, lvl in re.findall(r"(\d+)(?: are)? `([a-z-]+)`", m.group(4))}
    cells = Counter(enforcement_level(a, e) for a in MATRIX for e in EVENTS)
    assert stated == {lvl: cells[lvl] for lvl in LEVELS}


def test_the_basis_tally_matches_the_matrix():
    m = re.search(r"(\d+) of the (\d+) agents rest on vendor documentation, (.*?) on a third-party install", _PROSE)
    assert m, "llms.txt lost its basis tally"
    bases = Counter(basis(a) for a in MATRIX)
    assert (int(m.group(1)), int(m.group(2))) == (bases["vendor-docs"], len(MATRIX))
    rest = [int(n) for n in re.findall(r"(\d+) on", " " + m.group(3) + " on a third-party install")]
    assert rest == [bases[b] for b in ("live-run", "live-run-partial", "vendor-source", "third-party-install")]
