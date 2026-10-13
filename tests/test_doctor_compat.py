"""`doctor` names the other agents' configs grok also runs, when they carry our hooks."""

from __future__ import annotations

import argparse

from agentseam import install
from agentseam.adapters import get
from agentseam.cli_report import _cmd_doctor, compat_notes

GROK_COMPAT = (".claude/settings.json", ".claude/settings.local.json", ".cursor/hooks.json")


def test_grok_records_the_three_compat_files_it_reads():
    assert get("grok").ALSO_READS == GROK_COMPAT


def test_doctor_names_a_compat_file_grok_also_runs(tmp_path, capsys):
    install.install("claude_code", ["pre_tool"], "guard", repo_root=str(tmp_path))
    _cmd_doctor(argparse.Namespace(repo=str(tmp_path)))
    out = capsys.readouterr().out
    assert "also runs the agentseam hooks in .claude/settings.json; `uninstall grok` leaves them" in out


def test_a_compat_file_without_our_marker_is_not_named(tmp_path):
    (tmp_path / ".cursor").mkdir()
    (tmp_path / ".cursor" / "hooks.json").write_text('{"version": 1, "hooks": {}}')
    assert list(compat_notes("grok", str(tmp_path))) == []


def test_agents_that_read_no_other_config_get_no_note(tmp_path):
    install.install("claude_code", ["pre_tool"], "guard", repo_root=str(tmp_path))
    assert list(compat_notes("claude_code", str(tmp_path))) == []
    assert len(list(compat_notes("grok", str(tmp_path)))) == 1


def test_also_reads_travels_with_its_own_evidence():
    from agentseam.vendor_config import VENDOR_CONFIG

    for agent, entry in VENDOR_CONFIG.items():
        assert ("also_reads" in entry) == ("also_reads" in entry["evidence"]), agent
