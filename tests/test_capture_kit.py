"""The capture kit: installing the probe, spotting conflicts, and reporting what it caught.

The probe's own behaviour lives in test_capture_probe.py; redaction in test_redaction.py.
What is left here is the wiring -- which configs get written, which of them fire the same
probe twice, and whether the report says something true about what came back.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))


# Paths use /workspace/alice deliberately: the repository's own privacy scanner rejects a tracked
# file containing a realistic home directory, and it was right to reject the first version of


def test_install_wires_a_quoted_interpreter_and_the_agent_name(tmp_path, monkeypatch):
    """An unquoted interpreter under 'C:\\Program Files' never launches, which is
    indistinguishable at capture time from a vendor whose hooks do not fire."""
    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import argparse

    import capture

    capture.cmd_install(argparse.Namespace(agent="cursor", repo=str(tmp_path)))
    from agentseam import install as install_mod

    entry = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())

    def commands_in(obj):
        if isinstance(obj, dict):
            found = [obj["command"]] if isinstance(obj.get("command"), str) else []
            return found + [c for v in obj.values() for c in commands_in(v)]
        if isinstance(obj, list):
            return [c for v in obj for c in commands_in(v)]
        return []

    commands = commands_in(entry)
    assert commands, entry
    for command in commands:
        assert command.startswith('"%s" "' % sys.executable), command
        assert command.endswith(" cursor"), command
    assert install_mod.installed("cursor", str(tmp_path))


def test_every_adapter_can_be_detected():
    """A footprint per adapter, or `detect` silently cannot find agents we support.

    Junie and Tabnine were adapted after the capture kit was written and were missing here,
    so `capture.py detect` reported them absent on a machine that had them -- which reads as
    "you do not have it" rather than "we never looked".
    """
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
    import capture

    from agentseam import adapters

    missing = sorted(set(adapters.ADAPTERS) - set(capture.FOOTPRINTS))
    assert not missing, "adapters with no detection footprint: %s" % ", ".join(missing)


def _install(agent, repo, tmp_path, monkeypatch):
    import argparse

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path / ".capture"))
    sys.modules.pop("capture", None)
    import capture

    capture.cmd_install(argparse.Namespace(agent=agent, repo=str(repo)))
    return capture


def test_two_installs_in_one_repo_are_reported_as_a_conflict(tmp_path, monkeypatch, capsys):
    """Witnessed live: 27 payloads labelled `cursor` beside 26 labelled `?`, near 1:1.

    Cursor also loads Claude Code-format hooks, so a leftover .claude/settings.json entry
    fires the same probe on the same events -- once with the agent argument install wired,
    once without. Half the evidence then cannot be held against any adapter, and nothing in
    the kit said why.
    """
    import argparse

    capture = _install("cursor", tmp_path, tmp_path, monkeypatch)
    assert capture.cmd_conflicts(argparse.Namespace(repo=str(tmp_path))) == 0

    _install("claude_code", tmp_path, tmp_path, monkeypatch)
    capsys.readouterr()
    assert capture.cmd_conflicts(argparse.Namespace(repo=str(tmp_path))) == 1, "conflict not reported"
    out = capsys.readouterr().out
    assert "cursor" in out and "claude_code" in out and "twice" in out


def test_install_warns_when_another_config_here_already_fires_the_probe(tmp_path, monkeypatch, capsys):
    """The warning belongs at install time, while it is still cheap to act on."""
    _install("cursor", tmp_path, tmp_path, monkeypatch)
    capsys.readouterr()
    _install("claude_code", tmp_path, tmp_path, monkeypatch)
    assert "WARNING" in capsys.readouterr().out


def test_an_unlabelled_payload_is_not_reported_as_an_unknown_agent(tmp_path, monkeypatch, capsys):
    """`?` is not a vendor.

    Calling it "no adapter for this agent yet" reads as a discovery when it is a labelling
    miss, and sends the reader looking for a thirteenth agent that does not exist.
    """
    import argparse

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    (tmp_path / "captured.1.jsonl").write_text(
        json.dumps({"agent": "?", "payload": {"hook_event_name": "preToolUse"}}) + "\n"
    )
    capture.cmd_report(argparse.Namespace())
    out = capsys.readouterr().out
    assert "NOT a second vendor" in out
    assert "No adapter for this agent yet" not in out


def test_the_report_states_the_agent_version_it_captured(tmp_path, monkeypatch, capsys):
    """The matrix records a version per row, and the payload carries one.

    Redaction already lets it through -- `cursor_version` is on the structural allowlist and
    a version is enum-like -- but the report printed only key *paths*, so the fact sat in the
    capture file unread and had to be asked for by hand three times over.
    """
    import argparse

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    (tmp_path / "captured.1.jsonl").write_text(
        json.dumps(
            {
                "agent": "cursor",
                "payload": {"hook_event_name": "stop", "cursor_version": "1.5.11"},
            }
        )
        + "\n"
    )
    capture.cmd_report(argparse.Namespace())
    assert "agent version: 1.5.11" in capsys.readouterr().out


def test_a_redacted_placeholder_is_never_reported_as_a_version(tmp_path, monkeypatch, capsys):
    """A key merely containing "version" whose value did not survive redaction says nothing.

    Printing `<str:12>` as the agent version would put a placeholder into a matrix row, which
    is worse than leaving the field empty.
    """
    import argparse

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    (tmp_path / "captured.1.jsonl").write_text(
        json.dumps({"agent": "cursor", "payload": {"hook_event_name": "stop", "api_version": "<str:12>"}}) + "\n"
    )
    capture.cmd_report(argparse.Namespace())
    assert "agent version" not in capsys.readouterr().out
