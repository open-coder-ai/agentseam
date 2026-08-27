"""The probe program: what it records, what it answers, and what it must never do.

Split from the kit tests because the program that runs inside somebody else's agent is a
different activity from the commands that install it and report on it -- and because the
combined file crossed the 300-line review budget, where the remedy is splitting by activity
rather than raising the number.

Every test here runs the real generated probe as a subprocess. Inspecting its source would
only prove the source looks right; these prove what lands on disk and what reaches stdout.
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
    # Through the loader, not a fixed filename: the probe writes a per-process shard.
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
    """The exact failure a live Cursor run on Windows produced: the console locale turned a
    UTF-8 BOM into mojibake and a whole session was recorded only as lengths. Chock's gate
    hit the same byte-for-byte failure and its fix -- read bytes, decode utf-8-sig -- is
    ported here and pinned."""
    payload = json.dumps({"hook_event_name": "beforeShellExecution", "command": "echo hi"})
    for data in (b"\xef\xbb\xbf" + payload.encode("utf-8"), payload.encode("utf-16")):
        row = _run_probe(tmp_path, monkeypatch, data)
        assert row["payload"].get("hook_event_name") == "beforeShellExecution", row
        for shard in tmp_path.glob("captured*.jsonl"):
            shard.unlink()


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


def test_the_probe_answers_a_permission_gate_in_the_agents_own_dialect(tmp_path, monkeypatch):
    """Exit 0 is not an answer everywhere. Witnessed live: Cursor's beforeShellExecution
    got no output from the silent probe and REJECTED the user's real command -- the exact
    interference the probe promises never to cause. It now allows in-dialect."""
    payload = json.dumps({"hook_event_name": "beforeShellExecution", "command": "x", "cwd": "/w"})
    out = _probe_stdout(tmp_path, monkeypatch, payload.encode(), "cursor")
    assert json.loads(out) == {"permission": "allow"}


def test_the_probe_stays_silent_where_silence_is_the_protocol(tmp_path, monkeypatch):
    """Observational hooks document no output fields; inventing one risks the opposite bug."""
    payload = json.dumps({"hook_event_name": "afterFileEdit", "file_path": "/w/x.py", "edits": []})
    assert _probe_stdout(tmp_path, monkeypatch, payload.encode(), "cursor") == ""
    assert _probe_stdout(tmp_path, monkeypatch, b"not json", "cursor") == ""


def test_concurrent_probes_never_tear_a_record(tmp_path, monkeypatch):
    """Cursor runs subagents in parallel, so several probes append at once.

    Witnessed live: a shared append target produced two records split mid-string and the
    report died on the first fragment, taking 122 good records with it. Per-process shards
    remove the sharing rather than narrowing the window; this fires 64 probes concurrently
    with payloads large enough to make a buffered append tear.
    """
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
    """The other half of the same failure: a capture already torn must still report.

    Losing 122 good records to one bad line is the wrong trade, and dropping it silently
    would present a partial capture as a complete one.
    """
    monkeypatch.setenv("AGENTSEAM_CAPTURE_DIR", str(tmp_path))
    sys.modules.pop("capture", None)
    import capture

    whole_a = json.dumps({"agent": "cursor", "payload": {"hook_event_name": "stop"}})
    whole_b = json.dumps({"agent": "cursor", "payload": {"hook_event_name": "sessionStart"}})
    # The literal tail of a record torn mid-string, as seen in the live capture.
    fragment = 'er_email": "<str:29>", "workspace_roots": ["<str:40>"]}}'
    (tmp_path / "captured.jsonl").write_text("\n".join([whole_a, fragment, whole_b]) + "\n")

    rows = capture._load()
    assert len(rows) == 2 and capture._load.torn == 1
