"""Devin CLI adapter."""

from __future__ import annotations

import json as _json

from ..contract import (
    ASK,
    DENY,
    POST_TOOL,
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
from .claude_code import looks_like_claude_code

AGENT = "devin"

EVENT_MAP = {
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "PermissionRequest": PRE_TOOL,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "Stop": STOP,
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
}
REVERSE_EVENT_MAP = {
    PRE_TOOL: "PreToolUse",
    POST_TOOL: "PostToolUse",
    PROMPT_SUBMIT: "UserPromptSubmit",
    STOP: "Stop",
    SESSION_START: "SessionStart",
    SESSION_END: "SessionEnd",
}

_DEVIN_ONLY = ("PermissionRequest", "PostCompaction")

_CONTEXT_EVENTS = ("UserPromptSubmit", "SessionStart", "PostToolUse")


def claims(raw):
    """True only when the payload is distinguishable from Claude Code's."""
    if not isinstance(raw, dict):
        return False
    name = raw.get("hook_event_name")
    if name in _DEVIN_ONLY:
        return True
    return name in EVENT_MAP and "prompt_id" in raw and not looks_like_claude_code(raw)


def parse(raw):
    ti = raw.get("tool_input")
    ti = tool_input_of(ti)
    content = ti.get("content") or ti.get("new_string") or None
    out = raw.get("tool_output")
    if isinstance(out, (dict, list)):
        out = _json.dumps(out)
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
        tool=raw.get("tool_name"),
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("path"),
        content=content,
        output=out,
        prompt=raw.get("prompt"),
        session_id=raw.get("session_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


DECISION_VOCABULARY = frozenset({"approve", "block"})


_BLOCKING_EVENTS = ("PreToolUse", "PermissionRequest", "UserPromptSubmit", "Stop")


def respond(decision, event):
    name = (event.raw or {}).get("hook_event_name") or "PreToolUse"

    if name not in _BLOCKING_EVENTS:
        if decision.reason and name in _CONTEXT_EVENTS:
            body = {"hookEventName": name, "additionalContext": decision.reason}
            return _json.dumps({"hookSpecificOutput": body}), 0
        return "", 0

    if decision.outcome == REWRITE:
        if name == "PreToolUse" and decision.updated_input is not None:
            body = {"hookEventName": "PreToolUse", "updatedInput": decision.updated_input}
            return _json.dumps({"hookSpecificOutput": body}), 0
        return _json.dumps(
            {"decision": "block", "reason": decision.reason or "input requires modification before it can run"}
        ), 0

    if decision.outcome in (DENY, ASK):
        reason = decision.reason or "blocked by policy"
        if decision.outcome == ASK:
            note = (
                "Devin cannot modify a tool call"
                if degraded_from(decision) == REWRITE
                else "Devin cannot prompt for confirmation"
            )
            reason = "%s (%s, so this is a block)" % (reason, note)
        return _json.dumps({"decision": "block", "reason": reason}), 0

    if decision.reason and name in _CONTEXT_EVENTS:
        body = {"hookEventName": name, "additionalContext": decision.reason}
        return _json.dumps({"hookSpecificOutput": body}), 0
    return _json.dumps({"decision": "approve"}), 0


def hook_config(canonical_events, command, matcher=None):
    """Devin's own file. `.devin/hooks.v1.json` holds the hooks object as the whole file."""
    config = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        entry = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            entry["matcher"] = matcher
        config.setdefault(name, []).append(entry)
    return config


CONFIG_PATH = ".devin/hooks.v1.json"
