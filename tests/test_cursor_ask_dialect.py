"""The three facts R3's one-to-many note rests on, pinned so the note cannot rot.

R3 is record-only: no code changes until an ask-style Cursor policy consumer exists. But a
note nobody executes decays into folklore, and the resolution it records was already
established once by a live capture. These tests hold the facts in place so the day someone
does ship an ask policy, the constraint is a failing expectation rather than a rediscovery.
"""

from __future__ import annotations

from agentseam import adapters, install
from agentseam._data import load
from agentseam.adapters._hook_json import hj_reverse
from agentseam.contract import PRE_TOOL, Decision

CURSOR = load("vendors/cursor.json")

_PRE_TOOL_PAYLOAD = {
    "hook_event_name": "preToolUse",
    "conversation_id": "c1",
    "tool_name": "Bash",
    "tool_input": {"command": "rm -rf /"},
}
_SHELL_PAYLOAD = {
    "hook_event_name": "beforeShellExecution",
    "conversation_id": "c1",
    "command": "rm -rf /",
    "cwd": "/srv/checkout",
}


def test_the_reverse_map_is_one_to_one():
    """Fact 1: one wire name per canonical event. This is the limit R3 names."""
    reverse = hj_reverse(CURSOR)
    assert reverse[PRE_TOOL] == "preToolUse"
    assert all(isinstance(wire, str) for wire in reverse.values())


def test_ask_at_pre_tool_degrades_to_deny_and_says_so():
    """Fact 2: Cursor cannot prompt at preToolUse, and the adapter is honest about it."""
    adapter = adapters.get("cursor")
    event = adapter.parse(_PRE_TOOL_PAYLOAD)
    body, _rc = adapter.respond(Decision.escalate("confirm this"), event)
    assert '"permission": "deny"' in body
    assert "cannot prompt" in body


def test_ask_at_before_shell_execution_really_asks():
    """Fact 3: the gate that honours `ask` exists -- so the degrade above is a mapping choice."""
    adapter = adapters.get("cursor")
    event = adapter.parse(_SHELL_PAYLOAD)
    body, _rc = adapter.respond(Decision.escalate("confirm this"), event)
    assert '"permission": "ask"' in body


def test_both_payloads_parse_to_the_same_canonical_event():
    """Which is why one canonical name cannot pick the right gate on its own."""
    adapter = adapters.get("cursor")
    assert adapter.parse(_PRE_TOOL_PAYLOAD).event == PRE_TOOL
    assert adapter.parse(_SHELL_PAYLOAD).event == PRE_TOOL


def test_installing_at_pre_tool_wires_the_gate_that_cannot_ask(tmp_path):
    """The consequence worth recording: the install, not dispatch, is where `ask` is foreclosed."""
    path = install.install("cursor", [PRE_TOOL], "python guard.py", str(tmp_path))
    import json

    wired = json.load(open(path, encoding="utf-8"))["hooks"]
    assert list(wired) == ["preToolUse"]
    assert "beforeShellExecution" not in wired


def test_the_asking_gate_is_recorded_as_one_cursor_answers_at():
    """A future one-to-many map has somewhere to read the answer from, not a guess."""
    assert "beforeShellExecution" in CURSOR["verdicts"]["answer_events"]
    assert "beforeMCPExecution" in CURSOR["verdicts"]["answer_events"]
