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


def test_install_wires_a_launchable_interpreter_and_the_agent_name(tmp_path, monkeypatch):
    """The command must actually launch, which is not the same as being quoted.

    An unquoted interpreter under 'C:\\Program Files' never launches, and that is
    indistinguishable at capture time from a vendor whose hooks do not fire -- so quotes
    stay whenever the path has spaces. But quoting unconditionally has the same failure on
    the other side: PowerShell will not run a line beginning with a quoted path, and two
    vendors wrap hooks in PowerShell on Windows. So the rule is conditional, and this test
    asserts the property (it launches) rather than the spelling.
    """
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
        if " " in sys.executable:
            assert command.startswith('"%s" "' % sys.executable), command
        else:
            assert command.startswith("%s " % sys.executable), command
            assert not command.startswith('"'), "PowerShell cannot run a quoted-path line"
        assert command.endswith(" cursor"), command
    # capture installs under its own owner. Asking with the default owner used to answer
    # True purely because the substring witness matched "agentseam" inside
    # "agentseam-capture" -- a prefix collision that reported a guard nobody had installed.
    assert install_mod.installed("cursor", str(tmp_path), owner=capture.OWNER)
    assert not install_mod.installed("cursor", str(tmp_path)), "the capture probe is not a guard"


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


def test_key_paths_are_attributed_to_the_event_that_carried_them(tmp_path, monkeypatch, capsys):
    """A union across the session cannot say which event carries which key.

    That ambiguity blocked four follow-ups from one live run -- whether `tool_output`
    exists on failures, and which events carry `session_id`, could not be answered without
    another capture, even though every record on disk knew its own event name.
    """
    import argparse

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    rows = [
        {"agent": "cursor", "payload": {"hook_event_name": "preToolUse", "session_id": "<str:3>"}},
        {"agent": "cursor", "payload": {"hook_event_name": "postToolUseFailure", "error_message": "<str:9>"}},
    ]
    (tmp_path / "captured.1.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    capture.cmd_report(argparse.Namespace())
    out = capsys.readouterr().out

    pre = out.index("preToolUse:")
    fail = out.index("postToolUseFailure:")
    assert out.index("session_id") > pre, "session_id must sit under the event that carried it"
    assert fail < out.index("error_message") < pre, "error_message belongs under postToolUseFailure only"


def test_the_probe_command_is_runnable_by_powershell_too(monkeypatch):
    """The quoted form is correct for POSIX shells and cmd.exe and unrunnable in PowerShell,
    where a line beginning with a quoted path parses as a string expression rather than an
    invocation. Two vendors are now known to wrap hooks that way on Windows -- Codex, and
    VS Code Copilot via hookExecutor.ts's getShellCommand -- so a probe wired for either was
    recording nothing at all, silently.

    Those two carry a per-platform override in their own config schema. The other ten record
    no such field, so the command string is the only lever: an unquoted interpreter path
    parses in command mode in all three shells and needs no vendor support.
    """
    import capture

    monkeypatch.setattr(capture.sys, "executable", "C:/Python314/python.exe")
    command = capture._probe_command("C:/repo/.capture/probe.py", "cursor")
    assert not command.startswith('"'), "PowerShell will not run a line starting with a quote"
    assert command == 'C:/Python314/python.exe "C:/repo/.capture/probe.py" cursor'


def test_an_interpreter_path_with_spaces_keeps_its_quotes(monkeypatch):
    """There is no single string that runs in every shell when the path contains spaces, so
    the quoted form stays -- correct for POSIX and cmd -- rather than trading a working
    invocation on two shells for a broken one on three. install() warns in that case."""
    import capture

    monkeypatch.setattr(capture.sys, "executable", "C:/Program Files/Py/python.exe")
    command = capture._probe_command("C:/repo/probe.py", "cursor")
    assert command == '"C:/Program Files/Py/python.exe" "C:/repo/probe.py" cursor'


def test_detected_wires_every_agent_whose_config_location_exists(tmp_path, monkeypatch, capsys):
    """One capture evening should not have to guess which agent will be opened. The probe
    always allows, so an extra one costs a few recorded payloads; the benefit is that
    whichever agent is actually used is already recording."""
    import capture

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path / "cap"))
    monkeypatch.setattr(capture, "_detected_agents", lambda: ["claude_code", "cursor"])
    rc = capture.cmd_install(capture.argparse.Namespace(agent="detected", repo=str(tmp_path)))
    assert rc == 0
    out = capsys.readouterr().out
    assert "wiring 2 detected agent(s)" in out
    assert (tmp_path / ".claude" / "settings.json").exists()
    assert (tmp_path / ".cursor" / "hooks.json").exists()
