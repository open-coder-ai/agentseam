"""A documentation-silent reference reading is a disagreement only against a docs-grade claim."""

from __future__ import annotations

import copy

from agentseam import matrix
from agentseam.probe import experiment_report

UNKNOWN = {
    "agent": "claude_code",
    "trial": "unknown",
    "event": "pre_tool",
    "measured": {"unknown_verb_means": "undocumented"},
    "reading": "protocol is silent",
}


def test_docs_silence_beside_a_live_run_claim_is_named_not_counted(capsys):
    rc = experiment_report.render([UNKNOWN], agent="claude_code", event="pre_tool", driver="reference")
    assert rc == 0
    assert "docs-silent" in capsys.readouterr().out


def test_docs_silence_beside_a_docs_grade_claim_still_disagrees(monkeypatch):
    row = copy.deepcopy(matrix.MATRIX["claude_code"])
    row["events"]["pre_tool"]["evidence"]["unknown_verb_means"]["basis"] = "vendor-docs"
    monkeypatch.setitem(matrix.MATRIX, "claude_code", row)
    rows = experiment_report.diff_against_matrix([UNKNOWN])
    assert rows[0]["status"] == "DISAGREES"
