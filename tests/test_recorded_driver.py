"""The recorded driver: replays a frozen run instead of launching a real agent.

Two things matter here and are asserted directly, mirroring test_experiment_kit.py's own
split: that a replay goes through the real classifier (so it cannot silently drift from
what a live run would produce), and that the record/refuse invariants around `--record`
hold -- the same "only a real agent may claim live evidence" rule evidence_report.py
enforces on a submitted report.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import time

import pytest

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)

import experiment  # noqa: E402
import experiment_report  # noqa: E402
import recorded_driver  # noqa: E402

from agentseam import evidence_report  # noqa: E402

AGENT = "claude_code"
VERSION = "2.1.263"
WITNESSED = {
    "allow": {"baseline_ok": True},
    "deny": {"block": True},
    "crash": {"fail_mode": "open"},
    "silence": {"silence_means": "allow"},
    "timeout": {"timeout_fail_mode": "open"},
    "transform": {"transform": True},
    "unknown": {"unknown_verb_means": "allow"},
}


def test_the_seven_trials_reproduce_the_witnessed_table_in_under_a_second():
    started = time.time()
    results = [
        experiment.run_trial(AGENT, trial, event="pre_tool", driver="recorded", agent_version=VERSION)
        for trial in WITNESSED
    ]
    assert time.time() - started < 1.0
    for r in results:
        assert r["measured"] == WITNESSED[r["trial"]], r["trial"]
        assert r["driver"] == "recorded"
        assert r["workspace"] is None


def test_replay_goes_through_the_real_classifier_not_a_shortcut():
    """A recording that lied about its counts would produce a wrong classification --
    proving the replay path is `_classify` itself, not a stored answer."""
    r = experiment.run_trial(AGENT, "deny", event="pre_tool", driver="recorded", agent_version=VERSION)
    assert r["observed"] == {"runs": 0, "alt_runs": 0}
    assert r["hook_invocations"] == 1
    assert r["measured"] == {"block": True}


def test_diff_against_matrix_agrees_on_every_trial():
    results = [
        experiment.run_trial(AGENT, trial, event="pre_tool", driver="recorded", agent_version=VERSION)
        for trial in sorted(WITNESSED)
    ]
    rows = experiment_report.diff_against_matrix(results)
    disagreements = [row for row in rows if row["status"] == "DISAGREES"]
    assert disagreements == []


def test_a_trial_the_recording_never_covers_raises():
    with pytest.raises(recorded_driver.NoRecording):
        experiment.run_trial(AGENT, "deny", event="stop", driver="recorded", agent_version=VERSION)


def test_an_unwitnessed_version_raises():
    with pytest.raises(recorded_driver.NoRecording):
        experiment.run_trial(AGENT, "deny", event="pre_tool", driver="recorded", agent_version="0.0.1")


def test_an_agent_with_no_recording_has_none():
    assert recorded_driver.has_recording("no-such-agent") is False


def test_as_report_marks_the_recorded_basis_and_carries_recorded_version():
    results = [experiment.run_trial(AGENT, "deny", event="pre_tool", driver="recorded", agent_version=VERSION)]
    report = experiment_report.as_report(results, version=VERSION)
    assert report["driver"] == "recorded"
    assert report["recorded_version"] == VERSION
    # The seed recording covers only pre_tool, not every canonical experiment event.
    assert report["basis"] == "live-run-partial"


def test_a_recorded_report_claiming_a_newer_version_than_the_recording_is_rejected():
    results = [experiment.run_trial(AGENT, "deny", event="pre_tool", driver="recorded", agent_version=VERSION)]
    with pytest.raises(evidence_report.InvalidReportError, match="exceeds recorded_version"):
        experiment_report.as_report(results, version="99.0.0")


def test_a_recorded_report_may_still_claim_exactly_the_recorded_version():
    results = [experiment.run_trial(AGENT, "deny", event="pre_tool", driver="recorded", agent_version=VERSION)]
    assert experiment_report.as_report(results, version=VERSION)


# --- --record ----------------------------------------------------------------------


def test_record_refuses_the_reference_driver():
    with pytest.raises(SystemExit):
        experiment.main(["run", "--agent", AGENT, "--driver", "reference", "--record", "--agent-version", "1.0.0"])


def test_record_refuses_the_recorded_driver():
    with pytest.raises(SystemExit):
        experiment.main(["run", "--agent", AGENT, "--driver", "recorded", "--record", "--agent-version", "1.0.0"])


def test_record_requires_agent_version():
    with pytest.raises(SystemExit):
        experiment.main(["run", "--agent", AGENT, "--driver", "true", "--record"])


def test_record_round_trips_a_synthetic_run():
    """--record writes a file the recorded driver can then replay -- proven end to end."""
    scratch_version = "0.0.1-test"
    written = recorded_driver.recordings.path_for(AGENT, scratch_version)
    try:
        code = experiment.main(
            [
                "run",
                "--agent",
                AGENT,
                "--driver",
                "true",
                "--trial",
                "allow",
                "--record",
                "--agent-version",
                scratch_version,
                "--json",
            ]
        )
        assert code == 0
        assert os.path.exists(written)
        with open(written, encoding="utf-8") as fh:
            body = json.load(fh)
        assert body["agent"] == AGENT
        assert body["version"] == scratch_version
        assert body["driver"] == "real-agent"
        assert "allow" in body["events"]["pre_tool"]["trials"]
    finally:
        if os.path.exists(written):
            os.remove(written)


def test_record_leaves_no_scratch_workspace_behind():
    scratch_version = "0.0.2-test"
    path = None
    try:
        results = [
            experiment.run_trial(
                AGENT, "allow", event="pre_tool", driver="true", keep=True, agent_version=scratch_version
            )
        ]
        path = recorded_driver.record(
            agent=AGENT, version=scratch_version, event="pre_tool", results=results, platform=sys.platform
        )
        assert results[0]["workspace"] and os.path.isdir(results[0]["workspace"])
    finally:
        if results and results[0]["workspace"]:
            shutil.rmtree(results[0]["workspace"], ignore_errors=True)
        if path and os.path.exists(path):
            os.remove(path)


def test_the_default_driver_is_chosen_per_gate_not_per_agent():
    """claude_code@2.1.263 recorded pre_tool only: that gate replays, the others fall back to
    the reference instead of failing on a recording that never saw them."""
    assert recorded_driver.resolve_driver("claude_code", None, event="pre_tool") == recorded_driver.DRIVER_NAME
    assert recorded_driver.resolve_driver("claude_code", None, event="stop") == recorded_driver.REFERENCE_DRIVER
    assert (
        recorded_driver.resolve_driver("claude_code", None, event="prompt_submit") == recorded_driver.REFERENCE_DRIVER
    )
    assert recorded_driver.resolve_driver("tabnine", None, event="pre_tool") == recorded_driver.REFERENCE_DRIVER
    assert (
        recorded_driver.resolve_driver("claude_code", "reference", event="pre_tool") == recorded_driver.REFERENCE_DRIVER
    )
