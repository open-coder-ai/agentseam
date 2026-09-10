"""docs/witness-skeleton.json: the three coverage gaps only a real agent can close.

W1 (armed, wave 1) cannot produce a `witnessed` row -- no cloud session holds vendor
credentials (contract, "The constraint that shapes every brief"). Its deliverable here is
the exact `--record` commands the owner runs, and a skeleton report shaped like their
--report output that must fail evidence_report.validate() until it is actually filled in --
so an unfilled block can never be mistaken for real evidence.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from agentseam import evidence_report

SKELETON = json.loads((Path(__file__).resolve().parents[1] / "docs" / "witness-skeleton.json").read_text("utf-8"))


def test_the_skeleton_names_all_three_missing_gates():
    gates = {gap["gate"] for gap in SKELETON["gaps"]}
    assert gates == {"pre_tool", "prompt_submit", "stop"}
    escalate_gap = next(g for g in SKELETON["gaps"] if g["gate"] == "pre_tool")
    assert escalate_gap["trial"] == "escalate"


@pytest.mark.parametrize("gap", SKELETON["gaps"], ids=lambda g: g["gate"])
def test_every_command_targets_the_shipped_probe_verb(gap):
    """The owner's copy-paste command uses the promoted, shipped verb, not a dev-only script."""
    assert gap["command"].startswith("agentseam probe run --agent claude_code --event %s" % gap["gate"])
    assert "--record" in gap["command"]
    assert "--report" in gap["command"]


@pytest.mark.parametrize("gap", SKELETON["gaps"], ids=lambda g: g["gate"])
def test_an_unfilled_skeleton_report_is_rejected(gap):
    """The whole point: a blank block must never silently pass as a witnessed row."""
    with pytest.raises(evidence_report.InvalidReportError, match="missing required field"):
        evidence_report.validate(gap["report"])


@pytest.mark.parametrize("gap", SKELETON["gaps"], ids=lambda g: g["gate"])
def test_the_skeleton_shape_validates_once_actually_filled_in(gap):
    """Proves the blanks are the only thing standing between this and real evidence --
    the skeleton is a genuine template, not a shape that is simply broken."""
    filled = copy.deepcopy(gap["report"])
    filled.update(basis="live-run-partial", date="2026-09-15", version="2.1.270")
    filled["experiments"] = {"escalate_means": "prompted"} if gap["trial"] == "escalate" else {"block": True}
    assert evidence_report.validate(filled)
