"""tools/probe_ci.py: the CI gate that replays every recording and fails on disagreement.

Two things matter and are asserted directly: that the gate genuinely agrees with the
committed evidence today (so a green run means something), and that it can fail loudly --
a script that always exits 0 would defeat the entire point of wiring it into CI.
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import probe_ci  # noqa: E402


def test_the_committed_recording_agrees_with_the_matrix():
    checked, disagreements = probe_ci.check()
    assert checked > 0
    assert disagreements == []


def test_main_reports_checked_and_returns_zero_when_it_agrees(capsys):
    assert probe_ci.main() == 0
    out = capsys.readouterr().out
    assert "0 disagreement(s)" in out
    assert "checked across" in out


def test_main_fails_loudly_when_a_trial_disagrees(monkeypatch, capsys):
    """Breaking it on purpose: a script that cannot fail is decoration, not a gate."""

    def _lying_diff(results, event=None):  # noqa: ARG001
        return [{"trial": "deny", "field": "block", "measured": False, "asserted": True, "status": "DISAGREES"}]

    monkeypatch.setattr(probe_ci.experiment_report, "diff_against_matrix", _lying_diff)
    assert probe_ci.main() == 1
    out = capsys.readouterr().out
    assert "DISAGREES" in out
    assert "1 disagreement(s)" in out


def test_main_reports_zero_recordings_honestly(monkeypatch, capsys):
    """Silence is a measurement, not a pass (contract invariant 4): checking nothing must
    say so rather than print a clean '0 disagreements' that reads like success."""
    monkeypatch.setattr(probe_ci.recordings, "agents", lambda: [])
    assert probe_ci.main() == 0
    out = capsys.readouterr().out
    assert "0 trial(s) checked" in out
    assert "measurement of nothing, not a pass" in out
