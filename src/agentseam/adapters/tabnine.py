"""Tabnine CLI adapter."""

from __future__ import annotations

import json as _json

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
    degraded_from,
    tool_input_of,
)

AGENT = "tabnine"

EVENT_MAP = {
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "BeforeAgent": PROMPT_SUBMIT,
    "AfterAgent": STOP,
    "BeforeTool": PRE_TOOL,
    "AfterTool": POST_TOOL,
    "PreCompress": PRE_COMPACT,
}
REVERSE_EVENT_MAP = {
    SESSION_START: "SessionStart",
    SESSION_END: "SessionEnd",
    PROMPT_SUBMIT: "BeforeAgent",
    STOP: "AfterAgent",
    PRE_TOOL: "BeforeTool",
    POST_TOOL: "AfterTool",
    PRE_COMPACT: "PreCompress",
}

BLOCKING_EVENTS = ("BeforeAgent", "AfterAgent", "BeforeModel", "AfterModel", "BeforeTool", "AfterTool")

_BLOCKING_CANONICAL = (PROMPT_SUBMIT, STOP, PRE_TOOL, POST_TOOL)

MARKER = "timestamp"


def claims(raw):
    if not isinstance(raw, dict):
        return False
    return raw.get("hook_event_name") in EVENT_MAP and MARKER in raw


def parse(raw):
    ti = raw.get("tool_input")
    ti = tool_input_of(ti)
    out = raw.get("tool_output") or raw.get("tool_response")
    if isinstance(out, (dict, list)):
        out = _json.dumps(out)
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
        tool=raw.get("tool_name"),
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("path"),
        content=ti.get("content") or ti.get("new_string"),
        output=out,
        prompt=raw.get("prompt"),
        session_id=raw.get("session_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def _because(reason, note):
    return "%s (%s)" % (reason, note) if reason else note


#: Decision words this vendor accepts -- UNVERIFIED, and the only such entry here. Nothing
DECISION_VOCABULARY = frozenset({"allow", "deny"})


def respond(decision, event):
    name = (event.raw or {}).get("hook_event_name")
    if event.event not in _BLOCKING_CANONICAL and name not in BLOCKING_EVENTS:
        return "", 0

    if decision.outcome == DENY or decision.outcome == ASK or decision.outcome == REWRITE:
        reason = decision.reason
        if decision.outcome == ASK:
            note = (
                "Tabnine cannot modify a tool call"
                if degraded_from(decision) == REWRITE
                else "Tabnine cannot prompt for confirmation"
            )
            reason = _because(reason, note)
        elif decision.outcome == REWRITE:
            reason = _because(reason, "Tabnine cannot modify a tool call")
        return _json.dumps({"decision": "deny", "reason": reason or "blocked by policy"}), 0
    return _json.dumps({"decision": "allow"}), 0


def hook_config(canonical_events, command, matcher=None):
    hooks = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        entry = {"hooks": [{"type": "command", "command": command, "name": "agentseam"}]}
        if matcher:
            entry["matcher"] = matcher
        hooks.setdefault(name, []).append(entry)
    return {"hooks": hooks}


CONFIG_PATH = ".tabnine/agent/settings.json"
