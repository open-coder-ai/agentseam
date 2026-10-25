"""The maintainer's report printer shows a stranger's text as text, never as terminal control."""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import verify_report  # noqa: E402

from agentseam import evidence_report  # noqa: E402

CONTROL = ("\x1b", "\x07", "\x9b", "‮", "​", "\r")


def _report(**over):
    base = {
        "report_version": evidence_report.REPORT_VERSION,
        "agent": "claude_code",
        "basis": "vendor-docs",
        "driver": "real-agent",
        "version": "1.0.0",
        "date": "2026-10-01",
        "reporter": "someone",
    }
    base.update(over)
    return base


def test_no_field_reaches_the_terminal_with_a_control_character(capsys, tmp_path):
    hostile = "x\x1b[8m\x1b]52;c;AAAA\x07\x9b2K‮​\r\nWARNING forged"
    path = tmp_path / "r.json"
    path.write_text(json.dumps(_report(driver=hostile, version=hostile, reporter=hostile, date="2026-10-01" + hostile)))
    verify_report.main([str(path), "--diff"])
    out = capsys.readouterr().out
    assert not any(ch in out for ch in CONTROL)
    assert "\\x1b" in out
    assert "\nWARNING forged" not in out


def test_a_rejection_message_is_escaped_too(capsys, tmp_path):
    path = tmp_path / "r.json"
    path.write_text(json.dumps(_report(**{"bad\x1b[2Jkey": 1})))
    verify_report.main([str(path)])
    assert "\x1b" not in capsys.readouterr().out


def test_ordinary_text_is_unchanged():
    assert verify_report._plain("real-agent 1.0.0 (ünï)") == "real-agent 1.0.0 (ünï)"
