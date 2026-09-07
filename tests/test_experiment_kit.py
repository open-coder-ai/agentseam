"""The experiment harness, tested by running it -- not by reading its source.

Every assertion here goes through the real probe, the real adapter and the real reference
agent, for the same reason test_capture_kit.py does: a harness that produces evidence has
to be trustworthy in the same way the evidence is, and a mocked-out test of a measurement
tool measures nothing.

Two properties matter most and are asserted directly:

* **Isolation.** The probe interferes on purpose, so a leaked workspace or a config
  written outside it would be a genuine hazard, not a tidiness problem.
* **Falsifiability.** The harness must be able to report a disagreement. A measurement
  device that can only ever agree with the claim it is checking is decoration.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)

import experiment  # noqa: E402
import experiment_probe  # noqa: E402
import experiment_report  # noqa: E402
import reference_agent  # noqa: E402

AGENT = "claude_code"

#: Trials that finish in milliseconds. `timeout` is exercised separately with a short cap.
FAST = ("allow", "deny", "crash", "silence", "transform", "unknown")


@pytest.fixture(scope="module")
def results():
    return {t: experiment.run_trial(AGENT, t) for t in FAST}


def test_every_behaviour_is_documented():
    """A trial with no description would reach `list` as a blank line."""
    for name, text in experiment_probe.BEHAVIOURS.items():
        assert text.strip(), name
        assert text.endswith("."), name


def test_the_hook_is_actually_reached(results):
    """Distinguishes a real measurement from a config the agent never read."""
    for trial, r in results.items():
        assert r["hook_invocations"] >= 1, "%s: probe was never invoked" % trial


def test_baseline_allows(results):
    """If a permissive answer blocks, every other trial's result is meaningless."""
    assert results["allow"]["measured"] == {"baseline_ok": True}


def test_deny_blocks_and_crash_falls_open(results):
    """The two claims the README leads with, measured rather than asserted."""
    assert results["deny"]["measured"] == {"block": True}
    assert results["crash"]["measured"] == {"fail_mode": "open"}


def test_transform_replaces_the_input(results):
    assert results["transform"]["measured"] == {"transform": True}
    assert results["transform"]["observed"]["alt_runs"] == 1
    assert results["transform"]["observed"]["runs"] == 0


def test_unknown_verb_is_reported_as_undocumented(results):
    """The reference refuses to invent behaviour; that refusal is the finding. Named for the
    trial's own field (task 6) so the diff can compare it against a real agent's reading."""
    assert results["unknown"]["measured"] == {"unknown_verb_means": "undocumented"}
    assert "quarantine" in results["unknown"]["reading"]


def test_timeout_trial_is_measurable_with_a_short_cap():
    """The real sleep outlasts any vendor timeout, so the cap is what makes this testable."""
    r = experiment.run_trial(AGENT, "timeout", timeout=1)
    assert r["measured"] == {"timeout_fail_mode": "open"}
    assert r["outcome"]["gates"]["PreToolUse"]["timed_out"] is True


def test_workspaces_are_removed(results):
    """The probe denies and crashes: a leaked workspace is a hazard, not untidiness."""
    for trial, r in results.items():
        assert r["workspace"] is None, trial


def test_keep_leaves_an_inspectable_workspace(tmp_path):
    r = experiment.run_trial(AGENT, "deny", keep=True)
    try:
        assert r["workspace"] and os.path.isdir(r["workspace"])
        # The config the agent read must live inside the scratch dir, never outside it.
        config = os.path.join(r["workspace"], ".claude", "settings.json")
        assert os.path.exists(config)
        with open(config, encoding="utf-8") as fh:
            assert "PreToolUse" in json.load(fh)["hooks"]
    finally:
        import shutil

        shutil.rmtree(r["workspace"], ignore_errors=True)


def test_the_probe_answers_in_the_adapters_own_dialect():
    """Rendering runs through parse/respond, so a dialect bug surfaces here, not in prod."""
    src = experiment_probe.render("deny", "/tmp/record", agent=AGENT, src_dir="/tmp/src", trigger_alt="echo x")
    assert "adapter.parse(payload)" in src
    assert "adapter.respond(decision, event)" in src
    # The silent trials must not reach the adapter at all -- that is what makes them silent.
    for trial in experiment_probe.SILENT_TRIALS:
        body = experiment_probe.render(trial, "/tmp/r", agent=AGENT, src_dir="/tmp/s", trigger_alt="x")
        assert "TRIAL = %r" % trial in body


def test_harness_can_report_disagreement(results):
    """Falsifiability: a device that can only agree with the matrix is decoration."""
    rows = experiment_report.diff_against_matrix([results["deny"]])
    assert rows[0]["status"] == "agrees"

    lying = dict(results["deny"], measured={"block": False})
    rows = experiment_report.diff_against_matrix([lying])
    assert rows[0]["status"] == "DISAGREES"
    assert rows[0]["asserted"] is True


def test_fields_with_no_matrix_home_are_flagged_unrecorded(results):
    """`baseline_ok` is a run-health check (task 3, 2026-09-07), never a matrix claim."""
    rows = experiment_report.diff_against_matrix([results["allow"]])
    assert rows[0]["status"] == "unrecorded"


def test_a_recognized_field_the_cell_does_not_carry_is_unasserted():
    """`silence_means` is a real matrix field (task 3) -- absent from a cell, it is a claim
    never made, not a disagreement. claude_code's `stop` cell has never measured it."""
    r = experiment.run_trial(AGENT, "silence", event="stop")
    rows = experiment_report.diff_against_matrix([r], event="stop")
    assert rows[0]["field"] == "silence_means"
    assert rows[0]["status"] == "unasserted"
    assert rows[0]["asserted"] is None


def test_the_three_new_fields_are_recognized_by_the_diff():
    from agentseam import matrix_terms

    for field in ("silence_means", "timeout_fail_mode", "unknown_verb_means"):
        assert field in matrix_terms.CLAIM_FIELDS
        assert experiment_report._cell_key(field) == field


def test_claude_code_pre_tool_now_asserts_the_witnessed_fields(results):
    """Task 4's merge: silence, an unrecognised verb and a stall all now have a cell."""
    for trial, expected in (("silence", "allow"), ("unknown", "allow")):
        rows = experiment_report.diff_against_matrix([results[trial]])
        assert rows[0]["asserted"] == expected, trial
    timeout = experiment.run_trial(AGENT, "timeout", timeout=1)
    rows = experiment_report.diff_against_matrix([timeout])
    assert rows[0]["asserted"] == "open"


def test_the_reference_disagrees_with_the_witnessed_unknown_verb_reading():
    """The one trial reference and reality most plausibly differ on (task 6): the reference
    refuses to guess, the real agent was observed letting an unrecognised verb through."""
    r = experiment.run_trial(AGENT, "unknown")
    assert r["measured"] == {"unknown_verb_means": "undocumented"}
    rows = experiment_report.diff_against_matrix([r])
    assert rows[0]["status"] == "DISAGREES"
    assert rows[0]["asserted"] == "allow"


def test_reference_agent_refuses_to_guess():
    """Undocumented is raised, not defaulted -- a guess here would launder into evidence."""

    class _Proc:
        returncode = 0
        stdout = json.dumps({"hookSpecificOutput": {"permissionDecision": "quarantine"}})
        stderr = ""

    with pytest.raises(reference_agent.Undocumented):
        reference_agent._interpret(_Proc(), "G2")


# --- the two grammars -------------------------------------------------------------
#
# PreToolUse reads hookSpecificOutput.permissionDecision; Stop and UserPromptSubmit do
# not. That was established by a live run recorded in this repository's own evidence for
# claude_code, after the hooks reference proved ambiguous. These tests exist so the
# finding cannot be lost again -- an adapter that emits the G2 shape at a G1 gate looks
# exactly like one that is working.


class _Reply:
    def __init__(self, stdout="", returncode=0, stderr=""):
        self.stdout, self.returncode, self.stderr = stdout, returncode, stderr


_PERMISSION_DENY = json.dumps(
    {"hookSpecificOutput": {"hookEventName": "Stop", "permissionDecision": "deny", "permissionDecisionReason": "no"}}
)
_G1_DENY = json.dumps({"decision": "block", "reason": "no"})


def test_g1_gates_ignore_permission_decision():
    """The silent-allow that makes a wrong dialect indistinguishable from a working one."""
    decision, reason, _ = reference_agent._interpret(_Reply(_PERMISSION_DENY), "G1")
    assert decision == reference_agent.ALLOW
    assert "not read here" in reason


def test_g2_gates_honour_permission_decision():
    decision, _, _ = reference_agent._interpret(_Reply(_PERMISSION_DENY), "G2")
    assert decision == reference_agent.DENY


def test_g1_gates_honour_the_block_form():
    for grammar in ("G1", "G2"):
        decision, _, _ = reference_agent._interpret(_Reply(_G1_DENY), grammar)
        assert decision == reference_agent.DENY, grammar


def test_exit_two_blocks_under_either_grammar():
    for grammar in ("G1", "G2"):
        decision, _, _ = reference_agent._interpret(_Reply(returncode=2, stderr="nope"), grammar)
        assert decision == reference_agent.DENY, grammar


def test_the_adapter_speaks_the_right_dialect_at_every_gate():
    """If this fails, agentseam is emitting a shape the gate does not read."""
    from agentseam import adapters
    from agentseam import contract as ct

    adapter = adapters.get(AGENT)
    for wire, extra in (
        ("PreToolUse", {"tool_name": "Bash", "tool_input": {"command": "x"}}),
        ("UserPromptSubmit", {"prompt": "x"}),
        ("Stop", {"stop_hook_active": False}),
    ):
        raw = {"session_id": "s", "cwd": ".", "hook_event_name": wire}
        raw.update(extra)
        text, _ = adapter.respond(ct.Decision.deny("nope"), adapter.parse(raw))
        decision, _, _ = reference_agent._interpret(_Reply(text), reference_agent.GRAMMARS[wire])
        assert decision == reference_agent.DENY, "%s: deny was not honoured (emitted %s)" % (wire, text)


# --- gating at each event ---------------------------------------------------------


@pytest.mark.parametrize("event", experiment.EVENTS)
def test_deny_is_measurable_at_every_gate(event):
    r = experiment.run_trial(AGENT, "deny", event=event)
    assert r["measured"] == {"block": True}, "%s: %s" % (event, r["reading"])
    assert r["hook_invocations"] >= 1


@pytest.mark.parametrize("event", experiment.EVENTS)
def test_allow_never_blocks_at_any_gate(event):
    r = experiment.run_trial(AGENT, "allow", event=event)
    assert r["measured"] == {"baseline_ok": True}, "%s: %s" % (event, r["reading"])


def test_blocking_stop_shows_up_as_continuation_not_absence():
    """A Stop block has the opposite shape: the action happens MORE, not less."""
    r = experiment.run_trial(AGENT, "deny", event="stop")
    assert r["observed"]["runs"] > 1
    assert "made to continue" in r["reading"]


def test_blocking_the_prompt_gate_stops_the_tool_gate_being_reached():
    """Gate order is part of what an experiment measures."""
    r = experiment.run_trial(AGENT, "deny", event="prompt_submit", keep=True)
    try:
        assert r["observed"]["runs"] == 0
        assert r["outcome"]["gates"]["UserPromptSubmit"]["decision"] == "deny"
        assert "PreToolUse" not in r["outcome"]["gates"]
    finally:
        import shutil

        shutil.rmtree(r["workspace"], ignore_errors=True)


def test_an_unknown_event_is_refused_rather_than_silently_gating_nothing():
    with pytest.raises(ValueError, match="cannot gate at"):
        experiment.run_trial(AGENT, "deny", event="session_start")
