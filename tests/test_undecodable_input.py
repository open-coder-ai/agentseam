"""Input the hook cannot decode is refused, never read as an empty or silent allow."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentseam import adapters, bundler, dispatch  # noqa: E402
from agentseam.contract import Decision, UndecodableToolInputError, tool_input_of  # noqa: E402

DEEP = "[" * 100000 + "]" * 100000
HUGE_INT = "1" * 5000


def _payload(extra):
    return '{"hook_event_name":"PreToolUse","tool_name":"Bash","tool_input":{"command":"ls","z":%s}}' % extra


@pytest.mark.parametrize("extra", [DEEP, HUGE_INT])
def test_run_refuses_valid_json_it_cannot_decode(extra):
    code = dispatch.run(
        lambda _e: Decision.deny("no"), agent="claude_code", stdin=io.StringIO(_payload(extra)), exit=False
    )
    assert code == dispatch.DISPATCH_FAILURE_EXIT


def test_run_still_allows_silently_on_text_that_is_not_json():
    out = io.StringIO()
    assert dispatch.run(lambda _e: None, agent="claude_code", stdin=io.StringIO("{ nope"), stdout=out, exit=False) == 0
    assert out.getvalue() == ""


@pytest.mark.parametrize("text", ['{"command": "rm -rf x", "n": ' + HUGE_INT + "}", '{"a": ' + DEEP + "}"])
def test_string_form_tool_input_that_fails_to_decode_raises(text):
    with pytest.raises(UndecodableToolInputError):
        tool_input_of(text)


def test_string_form_tool_input_still_decodes():
    assert tool_input_of('{"command": "ls"}') == {"command": "ls"}
    assert tool_input_of(None) == {}


@pytest.mark.parametrize("agent", sorted(a for a in adapters.ADAPTERS if a in ("vscode_copilot", "claude_code")))
def test_dispatch_refuses_undecodable_string_tool_input(agent):
    key = "toolArgs" if agent == "vscode_copilot" else "tool_input"
    raw = {
        "hook_event_name": "PreToolUse",
        "toolName": "bash",
        "tool_name": "Bash",
        key: '{"command":"x","n":' + HUGE_INT + "}",
    }
    with pytest.raises(UndecodableToolInputError):
        dispatch.handle(raw, lambda _e: None, agent)
    code = dispatch.run(lambda _e: None, agent=agent, stdin=io.StringIO(json.dumps(raw)), exit=False)
    assert code == dispatch.DISPATCH_FAILURE_EXIT


def _bundle_exit(stdin_bytes, tmp_path):
    src = bundler.bundle("claude_code")
    start = src.index("# >>> agentseam handler >>>")
    end = src.index("# <<< agentseam handler <<<") + len("# <<< agentseam handler <<<")
    src = src[:start] + "def handle(event):\n    return None\n" + src[end:]
    path = tmp_path / "b.py"
    path.write_text(src, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-S", str(path)],
        input=stdin_bytes,
        capture_output=True,
        cwd=str(tmp_path),
        env={"PATH": os.environ.get("PATH", "")},
        timeout=60,
        check=False,
    )
    return proc.returncode, proc.stdout


@pytest.mark.parametrize("extra", [DEEP, HUGE_INT])
def test_the_bundled_runtime_refuses_valid_json_it_cannot_decode(extra, tmp_path):
    assert _bundle_exit(_payload(extra).encode(), tmp_path)[0] == 2


def test_the_bundled_runtime_refuses_undecodable_string_tool_input(tmp_path):
    raw = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": '{"command":"x","n":' + HUGE_INT + "}"}
    assert _bundle_exit(json.dumps(raw).encode(), tmp_path)[0] == 2


def test_the_bundled_runtime_still_allows_silently_on_text_that_is_not_json(tmp_path):
    assert _bundle_exit(b"{ nope", tmp_path) == (0, b"")
