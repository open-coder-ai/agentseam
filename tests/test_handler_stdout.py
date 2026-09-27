"""Stdout is the verdict channel: whatever a handler prints goes to stderr, never ahead of the JSON."""

from __future__ import annotations

import io
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import CC_BASH  # noqa: E402

from agentseam import bundler, dispatch  # noqa: E402
from agentseam.contract import Decision  # noqa: E402

_SRC = str(Path(__file__).resolve().parents[1] / "src")

_CHATTY = (
    "def handle(event):\n"
    "    import subprocess, sys\n"
    '    print("debug: inspecting", event.command)\n'
    '    subprocess.run([sys.executable, "-c", "print(\'child says hi\')"], check=False)\n'
    '    return Decision.deny("chatty-deny")\n'
)


def _chatty(event):
    print("debug: inspecting", event.command)
    return Decision.deny("chatty-deny")


def _verdict(text):
    return json.loads(text)["hookSpecificOutput"]["permissionDecision"]


def test_a_printing_handler_leaves_only_the_verdict_on_stdout(capsys):
    """Claude Code parsed `debug: ...{json}` as invalid, called it a non-blocking error, and
    ran the tool: the deny became an allow. The print belongs on stderr."""
    out = io.StringIO()
    code = dispatch.run(_chatty, stdin=io.StringIO(json.dumps(CC_BASH)), stdout=out, exit=False)
    assert code == 0
    assert _verdict(out.getvalue()) == "deny"
    captured = capsys.readouterr()
    assert "debug: inspecting" in captured.err
    assert "debug: inspecting" not in captured.out


def test_handle_keeps_a_handler_print_out_of_stdout_too(capsys):
    text, _code, _event, _decision = dispatch.handle(CC_BASH, _chatty, "claude_code")
    assert _verdict(text) == "deny"
    assert "debug" not in capsys.readouterr().out


def _run(argv, payload, tmp_path):
    return subprocess.run(
        argv,
        input=json.dumps(payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(tmp_path),
        env={"PATH": os.environ.get("PATH", ""), "PYTHONPATH": _SRC},
        timeout=30,
        check=False,
    )


def test_a_hook_process_whose_handler_and_its_child_print_still_emits_pure_json(tmp_path):
    """The child process writes to fd 1 directly, below sys.stdout; that is diverted too."""
    script = tmp_path / "hook.py"
    script.write_text(
        "from agentseam import Decision, dispatch\n\n" + _CHATTY + "\n\ndispatch.run(handle, agent='claude_code')\n",
        encoding="utf-8",
    )
    proc = _run([sys.executable, str(script)], CC_BASH, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert _verdict(proc.stdout.decode("utf-8")) == "deny"
    assert b"child says hi" in proc.stderr and b"debug: inspecting" in proc.stderr


def test_the_bundled_runtime_diverts_handler_output_the_same_way(tmp_path):
    src = bundler.bundle("claude_code")
    start = src.index("# >>> agentseam handler >>>")
    end = src.index("# <<< agentseam handler <<<") + len("# <<< agentseam handler <<<")
    path = tmp_path / "bundle.py"
    path.write_text(src[:start] + _CHATTY + src[end:], encoding="utf-8")
    proc = _run([sys.executable, "-S", str(path)], CC_BASH, tmp_path)
    assert proc.returncode == 0, proc.stderr
    assert _verdict(proc.stdout.decode("utf-8")) == "deny"
    assert b"child says hi" in proc.stderr and b"debug: inspecting" in proc.stderr
