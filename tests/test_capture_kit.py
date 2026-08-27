"""The capture kit's redaction is the part that must not be wrong.

It runs on a contributor's own machine, over payloads that can hold a prompt, a file being
written, a home directory or an email, and produces a file meant to be pasted into a PR. A
redactor that misses something has already leaked by the time anyone reads it.

So these tests assert the strong property rather than spot-checking known-sensitive keys:
**no string from the input may appear in the output**, except the short protocol enums on a
named allowlist.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import pytest  # noqa: E402
from redact import STRUCTURAL_KEYS, keys_of, redact  # noqa: E402

# Paths use /workspace/alice deliberately: the repository's own privacy scanner rejects a tracked
# file containing a realistic home directory, and it was right to reject the first version of
# this fixture. A test proving that secrets do not escape has no business shipping one.
SENSITIVE = {
    "hook_event_name": "PreToolUse",
    "tool_name": "Write",
    "session_id": "sess-9f3a-private",
    "cwd": "/workspace/alice/work",
    "user_email": "someone@example.com",
    "transcript_path": "/workspace/alice/.claude/transcript.jsonl",
    "prompt": "deploy using my key AKIA-not-real",
    "tool_input": {"file_path": "/workspace/alice/.env", "content": "TOKEN=hunter2"},
    "workspace_roots": ["/workspace/alice/repo", "/workspace/alice/other"],
    "nested": {"deep": {"deeper": "still private"}},
    "count": 7,
    "flag": True,
}


def _strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def test_no_input_string_survives_except_allowlisted_enums():
    """The property that matters. A denylist would miss the first field a vendor invents."""
    out = redact(SENSITIVE)
    allowed = {SENSITIVE[k] for k in STRUCTURAL_KEYS if isinstance(SENSITIVE.get(k), str)}
    leaked = [s for s in _strings(out) if s in set(_strings(SENSITIVE)) and s not in allowed]
    assert not leaked, "these input strings survived redaction: %s" % leaked


def test_the_protocol_enums_do_survive():
    """Otherwise a capture cannot tell us which event we are looking at, which is the point."""
    out = redact(SENSITIVE)
    assert out["hook_event_name"] == "PreToolUse"
    assert out["tool_name"] == "Write"


def test_a_structural_key_carrying_prose_is_still_redacted():
    """The allowlist is by key AND by shape, so a vendor reusing a name for something
    richer cannot smuggle content through it.
    """
    out = redact({"tool_name": "/workspace/alice/secret/path/with/separators"})
    assert out["tool_name"].startswith("<str:")

    long_value = {"source": "x" * 200}
    assert redact(long_value)["source"].startswith("<str:")


def test_structure_and_types_are_preserved_because_that_is_the_evidence():
    out = redact(SENSITIVE)
    assert out["count"] == 7 and out["flag"] is True
    assert set(keys_of(out)) >= {"tool_input", "tool_input.content", "nested.deep.deeper"}
    assert out["tool_input"]["content"].startswith("<str:")


def test_long_lists_are_summarized_not_dumped():
    out = redact({"items": ["a", "b", "c", "d"]})
    assert out["items"][-1] == "<...2 more>"


@pytest.mark.parametrize("value", [None, 3, 3.5, True, "plain", [], {}])
def test_redaction_never_raises_on_anything_a_vendor_might_send(value):
    json.dumps(redact({"k": value}))


def test_the_real_probe_allows_and_writes_nothing_sensitive(tmp_path, monkeypatch):
    """End to end against the generated probe, because that is what runs on a real machine.

    Inspecting the source would only prove the source looks right. This runs it over a
    payload full of things that must not travel and reads back what landed on disk.
    """
    import subprocess

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    probe = tmp_path / "probe.py"
    probe.write_text(capture._probe_source())

    result = subprocess.run([sys.executable, str(probe)], input=json.dumps(SENSITIVE), capture_output=True, text=True)
    assert result.returncode == 0, "the probe must always allow: %s" % result.stderr

    written = (tmp_path / "captured.jsonl").read_text()
    for secret in ("hunter2", "someone@example.com", "/workspace/alice", "sess-9f3a-private", "AKIA-not-real"):
        assert secret not in written, "%r reached the capture file" % secret
    assert "PreToolUse" in written and "tool_input" in written


def test_a_probe_over_unparseable_input_still_allows(tmp_path, monkeypatch):
    """A vendor sending something unexpected must not break the session being verified."""
    import subprocess

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    probe = tmp_path / "probe.py"
    probe.write_text(capture._probe_source())
    result = subprocess.run([sys.executable, str(probe)], input="not json at all", capture_output=True, text=True)
    assert result.returncode == 0


def _run_probe(tmp_path, monkeypatch, data, agent=("cursor",)):
    import subprocess

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    probe = tmp_path / "probe.py"
    probe.write_text(capture._probe_source())
    result = subprocess.run([sys.executable, str(probe), *agent], input=data, capture_output=True)
    assert result.returncode == 0, "the probe must always allow: %s" % result.stderr
    captured = tmp_path / "captured.jsonl"
    return json.loads(captured.read_text()) if captured.exists() else None


def test_a_bom_or_utf16_payload_still_parses(tmp_path, monkeypatch):
    """The exact failure a live Cursor run on Windows produced: the console locale turned a
    UTF-8 BOM into mojibake and a whole session was recorded only as lengths. Chock's gate
    hit the same byte-for-byte failure and its fix -- read bytes, decode utf-8-sig -- is
    ported here and pinned."""
    payload = json.dumps({"hook_event_name": "beforeShellExecution", "command": "echo hi"})
    for data in (b"\xef\xbb\xbf" + payload.encode("utf-8"), payload.encode("utf-16")):
        row = _run_probe(tmp_path, monkeypatch, data)
        assert row["payload"].get("hook_event_name") == "beforeShellExecution", row
        (tmp_path / "captured.jsonl").unlink()


def test_unparseable_input_records_why_not_just_how_much(tmp_path, monkeypatch):
    """A length alone cannot be diagnosed; 115 payloads of a real run proved it. The probe
    now records shape-only facts -- encoding, BOM, first character class, line counts --
    and still nothing of the content."""
    row = _run_probe(tmp_path, monkeypatch, b"Content-Length: 42\r\n\r\nnot json")
    diag = row["payload"]["__unparsed__"]
    assert diag["encoding"] == "utf-8-sig" and diag["bom"] == "none"
    assert diag["first_char"] == "letter" and diag["json_lines"] == 0
    assert "Content-Length" not in json.dumps(row)


def test_the_probe_knows_which_agent_it_records(tmp_path, monkeypatch):
    """Attribution rides argv: install wires it, so the report can hold the payloads
    against the right adapter instead of filing everything under '?'."""
    row = _run_probe(tmp_path, monkeypatch, b"{}", agent=("junie",))
    assert row["agent"] == "junie"


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
