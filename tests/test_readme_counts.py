"""The README's matrix tallies are recounted from `enforcement_level()` so they cannot drift."""

import re
from collections import Counter
from pathlib import Path

from agentseam.contract import EVENTS, PRE_TOOL
from agentseam.matrix import MATRIX, enforcement_level

README = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
LEVELS = ("none", "detect", "best-effort", "enforceable", "enforced")


def _cells():
    return Counter(enforcement_level(a, e) for a in MATRIX for e in EVENTS)


def test_the_cell_tally_line_matches_the_matrix():
    m = re.search(r"\*(\d+) cells \((\d+) agents by (\d+) events\).*?: (.*?)\.\*", README)
    assert m, "the README lost its cell tally line"
    assert [int(g) for g in m.groups()[:3]] == [len(MATRIX) * len(EVENTS), len(MATRIX), len(EVENTS)]
    stated = {lvl: int(n) for n, lvl in re.findall(r"(\d+) ([a-z-]+)", m.group(4))}
    assert stated == {lvl: _cells()[lvl] for lvl in LEVELS}


def test_every_enforced_of_total_claim_uses_the_real_total():
    claims = re.findall(r"(\d+) of (\d+) matrix cells are graded enforced", README)
    assert claims
    for enforced, total in claims:
        assert (int(enforced), int(total)) == (_cells()["enforced"], len(MATRIX) * len(EVENTS))


def test_the_pre_tool_level_table_counts_match_the_matrix():
    at_pre_tool = Counter(enforcement_level(a, PRE_TOOL) for a in MATRIX)
    for lvl in LEVELS:
        row = re.search(r"^\| %s \|[^|]*\| (none|\d+)\b" % re.escape(lvl), README, re.MULTILINE)
        assert row, lvl
        assert int(row.group(1).replace("none", "0")) == at_pre_tool[lvl], lvl
