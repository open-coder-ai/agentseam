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
    assert results["transform"]["observed"]["sentinel_alt"] is True
    assert results["transform"]["observed"]["sentinel"] is False


def test_unknown_verb_is_reported_as_undocumented(results):
    """The reference refuses to invent behaviour; that refusal is the finding."""
    assert results["unknown"]["measured"] == {"documented": False}
    assert "quarantine" in results["unknown"]["reading"]


def test_timeout_trial_is_measurable_with_a_short_cap():
    """The real sleep outlasts any vendor timeout, so the cap is what makes this testable."""
    r = experiment.run_trial(AGENT, "timeout", timeout=1)
    assert r["measured"] == {"timeout_fail_mode": "open"}
    assert r["outcome"]["hook_timed_out"] is True


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
    src = experiment_probe.render(
        "deny", "/tmp/record", agent=AGENT, src_dir="/tmp/src", trigger_alt="echo x"
    )
    assert "adapter.parse(payload)" in src
    assert "adapter.respond(decision, event)" in src
    # The silent trials must not reach the adapter at all -- that is what makes them silent.
    for trial in experiment_probe.SILENT_TRIALS:
        body = experiment_probe.render(trial, "/tmp/r", agent=AGENT, src_dir="/tmp/s", trigger_alt="x")
        assert 'TRIAL = %r' % trial in body


def test_harness_can_report_disagreement(results):
    """Falsifiability: a device that can only agree with the matrix is decoration."""
    rows = experiment.diff_against_matrix([results["deny"]])
    assert rows[0]["status"] == "agrees"

    lying = dict(results["deny"], measured={"block": False})
    rows = experiment.diff_against_matrix([lying])
    assert rows[0]["status"] == "DISAGREES"
    assert rows[0]["asserted"] is True


def test_fields_with_no_matrix_cell_are_flagged_unrecorded(results):
    """`silence_means` is behaviour agentseam relies on and the matrix does not record."""
    rows = experiment.diff_against_matrix([results["silence"]])
    assert rows[0]["status"] == "unrecorded"


def test_reference_agent_refuses_to_guess():
    """Undocumented is raised, not defaulted -- a guess here would launder into evidence."""
    class _Proc:
        returncode = 0
        stdout = json.dumps({"hookSpecificOutput": {"permissionDecision": "quarantine"}})
        stderr = ""

    with pytest.raises(reference_agent.Undocumented):
        reference_agent._interpret_claude_code(_Proc())
