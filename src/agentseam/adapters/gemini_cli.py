"""Gemini CLI adapter."""

from __future__ import annotations

from ..contract import (
    ASK,
    DENY,
    POST_TOOL,
    PRE_COMPACT,
    PRE_TOOL,
    PROMPT_SUBMIT,
    REWRITE,
    SESSION_END,
    SESSION_START,
    STOP,
    UNKNOWN,
    Event,
    tool_input_of,
)
from ._common import make_hook_config
from ._probes import looks_like_claude_code

AGENT = "gemini_cli"

EVENT_MAP = {
    "BeforeTool": PRE_TOOL,
    "AfterTool": POST_TOOL,
    "BeforeAgent": PROMPT_SUBMIT,
    "AfterAgent": STOP,
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "PreCompress": PRE_COMPACT,
}
REVERSE_EVENT_MAP = {v: k for k, v in EVENT_MAP.items()}

WRITE_TOOLS = ("write_file", "replace")
SHELL_TOOLS = ("run_shell_command",)


_OWN_CLIENT_TYPES = (None, "gemini_cli", "gemini")

_FOREIGN_MARKERS = (
    "timestamp",
    "project_path",
    "prompt_id",
    "turn_id",
)


def claims(raw):
    if not isinstance(raw, dict) or raw.get("hook_event_name") not in EVENT_MAP:
        return False
    if raw.get("client_type") not in _OWN_CLIENT_TYPES:
        return False
    if any(marker in raw for marker in _FOREIGN_MARKERS) or looks_like_claude_code(raw):
        return False
    return True


def parse(raw):
    ti = raw.get("tool_input")
    ti = tool_input_of(ti)
    tool = raw.get("tool_name")
    content = None
    if tool in WRITE_TOOLS:
        content = ti.get("content") or ti.get("new_string") or ti.get("new_str")
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
        tool=tool,
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("absolute_path") or ti.get("path"),
        content=content,
        output=raw.get("tool_output") or raw.get("tool_response"),
        prompt=raw.get("prompt") or raw.get("user_message"),
        session_id=raw.get("session_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


DECISION_VOCABULARY = frozenset({"allow", "deny", "ask"})

_ASK_EVENT = "BeforeTool"


_BLOCKING_EVENTS = ("BeforeTool", "AfterTool", "BeforeAgent", "AfterAgent")


def respond(decision, event):
    import json as _json

    name = (event.raw or {}).get("hook_event_name")
    if name not in _BLOCKING_EVENTS:
        return "", 0

    if decision.outcome == DENY:
        return _json.dumps({"decision": "deny", "reason": decision.reason or "blocked by policy"}), 0
    if decision.outcome == ASK:
        if name == _ASK_EVENT:
            return _json.dumps({"decision": "ask", "reason": decision.reason or "confirmation required"}), 0
        return (
            _json.dumps(
                {
                    "decision": "deny",
                    "reason": "%s (confirmation required; %s cannot prompt from a hook)"
                    % (decision.reason or "policy requires confirmation", name),
                }
            ),
            0,
        )
    if decision.outcome == REWRITE:
        return _json.dumps({"hookSpecificOutput": {"tool_input": decision.updated_input}}), 0
    return _json.dumps({"decision": "allow"}), 0


hook_config = make_hook_config(REVERSE_EVENT_MAP)


CONFIG_PATH = ".gemini/settings.json"
