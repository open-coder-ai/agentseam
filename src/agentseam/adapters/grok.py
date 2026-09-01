"""Grok CLI adapter."""

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
    SUBAGENT_START,
    SUBAGENT_STOP,
    TOOL_FAILURE,
    UNKNOWN,
    Event,
    degraded_from,
    tool_input_of,
)

AGENT = "grok"

EVENT_MAP = {
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "PostToolUseFailure": TOOL_FAILURE,
    "PermissionDenied": TOOL_FAILURE,
    "Stop": STOP,
    "StopFailure": STOP,
    "SubagentStart": SUBAGENT_START,
    "SubagentStop": SUBAGENT_STOP,
    "PreCompact": PRE_COMPACT,
    "PostCompact": PRE_COMPACT,
}
REVERSE_EVENT_MAP = {
    SESSION_START: "SessionStart",
    SESSION_END: "SessionEnd",
    PROMPT_SUBMIT: "UserPromptSubmit",
    PRE_TOOL: "PreToolUse",
    POST_TOOL: "PostToolUse",
    TOOL_FAILURE: "PostToolUseFailure",
    STOP: "Stop",
    SUBAGENT_START: "SubagentStart",
    SUBAGENT_STOP: "SubagentStop",
    PRE_COMPACT: "PreCompact",
}

BLOCKING_EVENT = "PreToolUse"


def claims(raw):
    """camelCase `hookEventName` carrying a PascalCase value is Grok's alone."""
    if not isinstance(raw, dict):
        return False
    return raw.get("hookEventName") in EVENT_MAP


def parse(raw):
    ti = raw.get("toolInput")
    ti = tool_input_of(ti)
    content = ti.get("content") or ti.get("new_string") or None
    out = raw.get("toolOutput")
    if isinstance(out, (dict, list)):
        out = _json.dumps(out)
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hookEventName"), UNKNOWN),
        tool=raw.get("toolName"),
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("path"),
        content=content,
        output=out,
        prompt=raw.get("prompt"),
        session_id=raw.get("sessionId"),
        cwd=raw.get("cwd") or raw.get("workspaceRoot"),
        raw=raw,
    )


DECISION_VOCABULARY = frozenset({"deny"})


def respond(decision, event):
    name = (event.raw or {}).get("hookEventName")
    if name != BLOCKING_EVENT:
        return "", 0

    if decision.outcome == REWRITE:
        return _json.dumps(
            {"decision": "deny", "reason": _because(decision.reason, "Grok cannot modify a tool call")}
        ), 0
    if decision.outcome == ASK:
        note = (
            "Grok cannot modify a tool call"
            if degraded_from(decision) == REWRITE
            else "Grok cannot prompt for confirmation"
        )
        return _json.dumps({"decision": "deny", "reason": _because(decision.reason, note)}), 0
    if decision.outcome == DENY:
        return _json.dumps({"decision": "deny", "reason": decision.reason or "blocked by policy"}), 0
    return "", 0


def _because(reason, note):
    """Keep the handler's reason and add why the outcome changed shape."""
    return "%s (%s)" % (reason, note) if reason else note


def hook_config(canonical_events, command, matcher=None):
    hooks = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        entry = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            entry["matcher"] = matcher
        hooks.setdefault(name, []).append(entry)
    return {"hooks": hooks}


NEEDS_TRUST = True

CONFIG_PATH = ".grok/hooks/agentseam.json"
