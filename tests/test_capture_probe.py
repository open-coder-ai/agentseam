"""The probe program: what it records, what it answers, and what it must never do."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))


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


def _run_probe(tmp_path, monkeypatch, data, agent=("cursor",)):
    import subprocess

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    probe = tmp_path / "probe.py"
    probe.write_text(capture._probe_source())
    result = subprocess.run([sys.executable, str(probe), *agent], input=data, capture_output=True)
    assert result.returncode == 0, "the probe must always allow: %s" % result.stderr
    _run_probe.stdout = result.stdout.decode()
    rows = capture._load()
    return rows[0] if rows else None


def _probe_stdout(tmp_path, monkeypatch, data, agent):
    import subprocess

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    probe = tmp_path / "probe.py"
    probe.write_text(capture._probe_source())
    result = subprocess.run([sys.executable, str(probe), agent], input=data, capture_output=True)
    assert result.returncode == 0, result.stderr
    return result.stdout.decode()


def test_the_real_probe_allows_and_writes_nothing_sensitive(tmp_path, monkeypatch):
    """End to end against the generated probe, because that is what runs on a real machine."""
    import subprocess

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    probe = tmp_path / "probe.py"
    probe.write_text(capture._probe_source())

    result = subprocess.run([sys.executable, str(probe)], input=json.dumps(SENSITIVE), capture_output=True, text=True)
    assert result.returncode == 0, "the probe must always allow: %s" % result.stderr

    written = "".join(open(shard).read() for shard in capture._capture_files())
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


def test_a_bom_or_utf16_payload_still_parses(tmp_path, monkeypatch):
    """The exact failure a live Cursor run on Windows produced: the console locale turned a"""
    payload = json.dumps({"hook_event_name": "beforeShellExecution", "command": "echo hi"})
    for data in (b"\xef\xbb\xbf" + payload.encode("utf-8"), payload.encode("utf-16")):
        row = _run_probe(tmp_path, monkeypatch, data)
        assert row["payload"].get("hook_event_name") == "beforeShellExecution", row
        for shard in tmp_path.glob("captured*.jsonl"):
            shard.unlink()


def test_unparseable_input_records_why_not_just_how_much(tmp_path, monkeypatch):
    """A length alone cannot be diagnosed; 115 payloads of a real run proved it. The probe"""
    row = _run_probe(tmp_path, monkeypatch, b"Content-Length: 42\r\n\r\nnot json")
    diag = row["payload"]["__unparsed__"]
    assert diag["encoding"] == "utf-8-sig" and diag["bom"] == "none"
    assert diag["first_char"] == "letter" and diag["json_lines"] == 0
    assert "Content-Length" not in json.dumps(row)


def test_the_probe_knows_which_agent_it_records(tmp_path, monkeypatch):
    """Attribution rides argv: install wires it, so the report can hold the payloads"""
    row = _run_probe(tmp_path, monkeypatch, b"{}", agent=("junie",))
    assert row["agent"] == "junie"


def test_the_probe_answers_a_permission_gate_in_the_agents_own_dialect(tmp_path, monkeypatch):
    """Exit 0 is not an answer everywhere. Witnessed live: Cursor's beforeShellExecution"""
    payload = json.dumps({"hook_event_name": "beforeShellExecution", "command": "x", "cwd": "/w"})
    out = _probe_stdout(tmp_path, monkeypatch, payload.encode(), "cursor")
    assert json.loads(out) == {"permission": "allow"}


def test_the_probe_stays_silent_where_silence_is_the_protocol(tmp_path, monkeypatch):
    """Observational hooks document no output fields; inventing one risks the opposite bug."""
    payload = json.dumps({"hook_event_name": "afterFileEdit", "file_path": "/w/x.py", "edits": []})
    assert _probe_stdout(tmp_path, monkeypatch, payload.encode(), "cursor") == ""
    assert _probe_stdout(tmp_path, monkeypatch, b"not json", "cursor") == ""


def test_concurrent_probes_never_tear_a_record(tmp_path, monkeypatch):
    """Cursor runs subagents in parallel, so several probes append at once."""
    import concurrent.futures
    import subprocess

    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    probe = tmp_path / "probe.py"
    probe.write_text(capture._probe_source())
    payload = json.dumps(
        {
            "hook_event_name": "preToolUse",
            "conversation_id": "c",
            "generation_id": "g",
            "cursor_version": "1.0",
            "workspace_roots": ["/w"],
            "tool_name": "Bash",
            "tool_input": {"command": "x" * 3000, "cwd": "/w"},
        }
    ).encode()

    def fire(_):
        return subprocess.run([sys.executable, str(probe), "cursor"], input=payload, capture_output=True).returncode

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        assert set(pool.map(fire, range(64))) == {0}

    rows = capture._load()
    assert capture._load.torn == 0, "%d record(s) torn by concurrent writes" % capture._load.torn
    assert len(rows) == 64, "expected 64 records, got %d" % len(rows)


def test_a_torn_line_is_skipped_and_counted_not_fatal(tmp_path, monkeypatch):
    """The other half of the same failure: a capture already torn must still report."""
    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    whole_a = json.dumps({"agent": "cursor", "payload": {"hook_event_name": "stop"}})
    whole_b = json.dumps({"agent": "cursor", "payload": {"hook_event_name": "sessionStart"}})
    fragment = 'er_email": "<str:29>", "workspace_roots": ["<str:40>"]}}'
    (tmp_path / "captured.jsonl").write_text("\n".join([whole_a, fragment, whole_b]) + "\n")

    rows = capture._load()
    assert len(rows) == 2 and capture._load.torn == 1


CURSOR_PRE_TOOL = {
    "hook_event_name": "preToolUse",
    "conversation_id": "c1",
    "generation_id": "g1",
    "cursor_version": "3.17.8",
    "workspace_roots": ["/workspace/alice/repo"],
    "tool_name": "Shell",
    "tool_input": {"command": "cat report.txt"},
}


def test_the_probe_answers_the_agent_that_sent_the_payload_not_the_one_it_was_installed_as(tmp_path, monkeypatch):
    """The probe used to pick its dialect from argv -- the label it was INSTALLED under --"""
    _run_probe(tmp_path, monkeypatch, json.dumps(CURSOR_PRE_TOOL).encode(), agent=("claude_code",))
    assert json.loads(_run_probe.stdout) == {"permission": "allow"}


def test_the_record_is_still_attributed_to_the_installed_label(tmp_path, monkeypatch):
    """Only the DIALECT moved to detection. Which config fired the probe is a real fact"""
    row = _run_probe(tmp_path, monkeypatch, json.dumps(CURSOR_PRE_TOOL).encode(), agent=("claude_code",))
    assert row["agent"] == "claude_code"


def test_an_unnameable_event_gets_no_invented_dialect(tmp_path, monkeypatch):
    """parse() resolves an unmapped event to UNKNOWN. There is no recorded output contract"""
    unknown = dict(CURSOR_PRE_TOOL, hook_event_name="somethingBrandNew")
    _run_probe(tmp_path, monkeypatch, json.dumps(unknown).encode(), agent=("cursor",))
    assert _run_probe.stdout == ""


def test_a_payload_no_adapter_claims_is_not_answered_in_the_argv_dialect(tmp_path, monkeypatch):
    """detect() declines on a genuine tie, and the argv fallback exists for that case --"""
    _run_probe(tmp_path, monkeypatch, json.dumps({"totally": "foreign"}).encode(), agent=("claude_code",))
    assert _run_probe.stdout == ""
