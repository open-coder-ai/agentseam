"""The `escalate` trial (W55): a three-value field the sentinel alone cannot classify.

Split from test_experiment_kit.py by activity (and to stay under the line budget): those
tests exercise the harness generally, these are specific to the one trial whose answer
depends on the driver's own outcome as well as the sentinel.
"""

from __future__ import annotations

import os
import sys

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)

import experiment  # noqa: E402
import experiment_escalate  # noqa: E402
import experiment_probe  # noqa: E402
import experiment_report  # noqa: E402
import reference_agent  # noqa: E402

AGENT = "claude_code"


class _Reply:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


def test_escalate_is_documented():
    assert "escalate" in experiment_probe.BEHAVIOURS


def test_the_reference_cannot_settle_pre_tool_escalate():
    """PreToolUse recognises `permissionDecision: "ask"` but nothing says what a headless
    run does next -- the same refusal-to-guess as the unknown-verb trial (task 6, W53)."""
    r = experiment.run_trial(AGENT, "escalate")
    assert r["measured"] == {"escalate_means": "undocumented"}
    assert "headless run" in r["reading"]
    reply = _Reply('{"hookSpecificOutput": {"permissionDecision": "ask"}}')
    with pytest.raises(reference_agent.Undocumented):
        reference_agent._interpret(reply, "G2")


def test_a_gate_that_does_not_honour_escalate_degrades_to_a_real_block():
    """Stop's gate never sees the ambiguous "ask" at all: it degrades to a block, which the
    reference reads exactly as it reads any other refusal."""
    r = experiment.run_trial(AGENT, "escalate", event="stop")
    assert r["measured"] == {"escalate_means": "refusal-or-error"}


def test_the_field_is_recognized_by_the_diff_and_starts_unasserted():
    from agentseam import matrix_terms

    assert matrix_terms.CLAIM_ESCALATE_MEANS in matrix_terms.CLAIM_FIELDS
    r = experiment.run_trial(AGENT, "escalate")
    rows = experiment_report.diff_against_matrix([r])
    assert rows[0]["field"] == "escalate_means"
    assert rows[0]["status"] == "unasserted"
    assert rows[0]["asserted"] is None


def test_cursor_renders_escalate_as_ask():
    """P7 (org-plan plan/agentseam-project.md): the ask row, in Cursor's own dialect."""
    from agentseam import adapters, contract

    adapter = adapters.get("cursor")
    raw = {
        "hook_event_name": "beforeShellExecution",
        "command": "echo hi",
        "cwd": ".",
        "conversation_id": "c1",
    }
    event = adapter.parse(raw)
    text, code = adapter.respond(contract.Decision.escalate("need confirmation"), event)
    assert code == 0
    assert '"ask"' in text


def test_an_agent_that_cannot_escalate_degrades_to_its_own_block_dialect():
    from agentseam import adapters, contract

    adapter = adapters.get("codex_cli")
    raw = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "x"}}
    event = adapter.parse(raw)
    text, code = adapter.respond(contract.Decision.escalate("need confirmation"), event)
    assert code == 0
    assert '"permissionDecision": "deny"' in text
    assert "does not support ask" in text


# --- classify_escalate, tested directly (no live driver in CI can ever stall) -------------


def test_not_blocked_reads_as_allow():
    field, value, reading = experiment_escalate.classify_escalate(False, None)
    assert (field, value) == ("escalate_means", "allow")
    assert "despite" in reading


def test_blocked_with_a_clean_driver_exit_reads_as_refusal_or_error():
    field, value, reading = experiment_escalate.classify_escalate(True, {"returncode": 0, "timed_out": False})
    assert (field, value) == ("escalate_means", "refusal-or-error")
    assert "without ever running" in reading


def test_blocked_with_a_stalled_driver_reads_as_prompted():
    """A headless driver that hangs (or is killed) waiting for an answer nobody gave is a
    different shape from a definite refusal -- the whole reason this trial exists."""
    for outcome in ({"returncode": None, "timed_out": True}, {"returncode": 1, "timed_out": False}):
        field, value, reading = experiment_escalate.classify_escalate(True, outcome)
        assert (field, value) == ("escalate_means", "prompted"), outcome
        assert "waiting" in reading


def test_the_reference_driver_never_stalls():
    """Fully scripted, so its outcome can never read as a stall -- only a real driver can."""
    assert not experiment_escalate.driver_stalled({"gates": {}, "action_runs": 0, "continuations": 0})
    assert not experiment_escalate.driver_stalled(None)
