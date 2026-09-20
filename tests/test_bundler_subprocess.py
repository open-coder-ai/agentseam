"""The bundler's real claim, proven rather than asserted: a vendored bundle run as a"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from scenarios import SCENARIOS  # noqa: E402

from agentseam import bundler, dispatch  # noqa: E402
from agentseam.contract import Decision  # noqa: E402


def _raise(_event):
    raise RuntimeError("policy bug")


_HANDLERS = {
    "allow": ("def handle(event):\n    return None\n", lambda event: None),
    "deny": (
        'def handle(event):\n    return Decision.deny("blocked-by-test")\n',
        lambda event: Decision.deny("blocked-by-test"),
    ),
    "rewrite": (
        'def handle(event):\n    return Decision.rewrite({"content": "safe"}, "needs change")\n',
        lambda event: Decision.rewrite({"content": "safe"}, "needs change"),
    ),
    "vouch": (
        'def handle(event):\n    return Decision.vouch("trusted")\n',
        lambda event: Decision.vouch("trusted"),
    ),
    # A handler defect must land on the same wire output as the library's own refusal.
    "raise": (
        'def handle(event):\n    raise RuntimeError("policy bug")\n',
        _raise,
    ),
}


def _inject_handler(src, handler_source):
    start = src.index("# >>> agentseam handler >>>")
    end = src.index("# <<< agentseam handler <<<") + len("# <<< agentseam handler <<<")
    return src[:start] + handler_source + src[end:]


def _run_bundle(src, raw_payload, tmp_path, name):
    path = tmp_path / ("%s.py" % name)
    path.write_text(src, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-S", str(path)],
        input=json.dumps(raw_payload).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(tmp_path),
        env={"PATH": os.environ.get("PATH", "")},
        timeout=30,
    )
    return proc.stdout.decode("utf-8"), proc.returncode, proc.stderr.decode("utf-8", errors="replace")


def _representative_event(agent):
    if "pre_tool" in SCENARIOS[agent]:
        return "pre_tool"
    return next(iter(SCENARIOS[agent]))


@pytest.mark.parametrize("agent", sorted(SCENARIOS))
@pytest.mark.parametrize("outcome", sorted(_HANDLERS))
def test_bundle_subprocess_matches_the_installed_adapter(agent, outcome, tmp_path):
    event = _representative_event(agent)
    raw = SCENARIOS[agent][event]
    handler_source, handler_fn = _HANDLERS[outcome]

    expected_text, expected_code, _event, _decision = dispatch.handle(raw, handler_fn, agent)

    bundled = _inject_handler(bundler.bundle(agent), handler_source)
    actual_text, actual_code, stderr = _run_bundle(bundled, raw, tmp_path, "%s-%s" % (agent, outcome))

    assert actual_code == expected_code, "%s/%s/%s: exit %r != %r\nstderr: %s" % (
        agent,
        event,
        outcome,
        actual_code,
        expected_code,
        stderr,
    )
    assert actual_text == expected_text, "%s/%s/%s: %r != %r" % (agent, event, outcome, actual_text, expected_text)


def test_a_payload_this_adapter_does_not_recognise_allows_silently_in_the_bundle_too(tmp_path):
    """Mirrors dispatch.handle()'s own contract for an unmapped event: handle() is never"""
    handler_source, handler_fn = _HANDLERS["deny"]
    raw = {"hook_event_name": "SomeFutureEventNoAdapterMapsYet"}

    expected_text, expected_code, _event, _decision = dispatch.handle(raw, handler_fn, "claude_code")
    bundled = _inject_handler(bundler.bundle("claude_code"), handler_source)
    actual_text, actual_code, stderr = _run_bundle(bundled, raw, tmp_path, "unmapped-event")

    assert actual_code == expected_code, stderr
    assert actual_text == expected_text


def test_malformed_stdin_allows_silently_in_the_bundle_too(tmp_path):
    handler_source, _handler_fn = _HANDLERS["deny"]
    bundled = _inject_handler(bundler.bundle("claude_code"), handler_source)
    path = tmp_path / "malformed.py"
    path.write_text(bundled, encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-S", str(path)],
        input=b"{ this is not json ,,,",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(tmp_path),
        env={"PATH": os.environ.get("PATH", "")},
        timeout=30,
    )
    assert proc.returncode == 0, proc.stderr.decode("utf-8", errors="replace")
    assert proc.stdout == b""


def test_the_unmodified_handler_stub_fails_loudly_rather_than_allowing_everything(tmp_path):
    """An un-filled-in bundle must not quietly behave like an always-allow guard -- that is

    the one way it could do harm. It used to die with exit 1, which is loud on a terminal and
    a non-blocking error to the host: the tool ran anyway. Now it refuses in the vendor's own
    dialect, names NotImplementedError in the reason, and still prints the traceback."""
    src = bundler.bundle("claude_code")
    raw = SCENARIOS["claude_code"]["pre_tool"]
    text, code, stderr = _run_bundle(src, raw, tmp_path, "unfilled")
    assert "NotImplementedError" in stderr
    verdict = json.loads(text)["hookSpecificOutput"]
    assert (code, verdict["permissionDecision"]) == (0, "deny")
    assert "NotImplementedError" in verdict["permissionDecisionReason"]
    assert "fill in your policy" not in text, "the exception's message must not reach the host"


def test_a_raising_handler_prints_its_traceback_to_stderr_in_the_bundle_too(tmp_path):
    handler_source, _handler_fn = _HANDLERS["raise"]
    bundled = _inject_handler(bundler.bundle("cursor"), handler_source)
    text, code, stderr = _run_bundle(bundled, SCENARIOS["cursor"]["pre_tool"], tmp_path, "raising")
    assert "RuntimeError: policy bug" in stderr
    assert (code, json.loads(text)["permission"]) == (0, "deny")
    assert "policy bug" not in text


@pytest.mark.skipif(os.name == "nt", reason="closing fd 2 before exec is a POSIX preexec_fn")
def test_a_bundle_with_no_stderr_keeps_its_traceback_out_of_the_verdict(tmp_path):
    """With fd 2 closed at startup, sys.stderr is None and the traceback module's default
    print goes to STDOUT -- inside the JSON the host parses. The verdict must be all there is."""
    handler_source, handler_fn = _HANDLERS["raise"]
    raw = SCENARIOS["claude_code"]["pre_tool"]
    expected_text, expected_code, _event, _decision = dispatch.handle(raw, handler_fn, "claude_code")
    path = tmp_path / "no-stderr.py"
    path.write_text(_inject_handler(bundler.bundle("claude_code"), handler_source), encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, "-S", str(path)],
        input=json.dumps(raw).encode("utf-8"),
        stdout=subprocess.PIPE,
        cwd=str(tmp_path),
        env={"PATH": os.environ.get("PATH", "")},
        preexec_fn=lambda: os.close(2),  # noqa: PLW1509 (a single-threaded test process; fd 2 gone is the point)
        timeout=30,
        check=False,
    )
    assert (proc.stdout.decode("utf-8"), proc.returncode) == (expected_text, expected_code)
