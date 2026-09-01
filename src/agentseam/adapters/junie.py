"""Junie CLI adapter."""

from __future__ import annotations

import json as _json

from ..contract import (
    ALLOW,
    ASK,
    DENY,
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

AGENT = "junie"

EVENT_MAP = {
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "PreToolUse": PRE_TOOL,
    "PermissionRequest": PRE_TOOL,
    "Stop": STOP,
}
REVERSE_EVENT_MAP = {
    SESSION_START: "SessionStart",
    SESSION_END: "SessionEnd",
    PROMPT_SUBMIT: "UserPromptSubmit",
    PRE_TOOL: "PreToolUse",
    STOP: "Stop",
}

MARKER = "project_path"

BLOCKING_EVENTS = ("UserPromptSubmit", "PreToolUse", "PermissionRequest", "Stop")


def claims(raw):
    if not isinstance(raw, dict):
        return False
    return raw.get("hook_event_name") in EVENT_MAP and MARKER in raw


def parse(raw):
    ti = raw.get("tool_input")
    ti = tool_input_of(ti)
    content = ti.get("content") or ti.get("new_string") or ti.get("new_source") or None
    if content is None and isinstance(ti.get("edits"), list):
        joined = "\n".join(str(e.get("new_string", "")) for e in ti["edits"] if isinstance(e, dict))
        content = joined or None
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
        tool=raw.get("tool_name"),
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("path") or ti.get("notebook_path"),
        content=content,
        output=raw.get("last_assistant_message"),
        prompt=raw.get("prompt"),
        session_id=raw.get("session_id"),
        cwd=raw.get("cwd") or raw.get("project_path"),
        raw=raw,
    )


DECISION_VOCABULARY = frozenset({"allow", "ask", "block"})


def respond(decision, event):
    name = (event.raw or {}).get("hook_event_name")
    if name not in BLOCKING_EVENTS:
        return "", 0

    if name == "Stop":
        if decision.outcome in (DENY, ASK, REWRITE):
            return _json.dumps({"decision": "block", "reason": decision.reason or "not finished"}), 0
        return "", 0

    if decision.outcome == REWRITE and decision.updated_input is not None:
        body = {"decision": "allow", "updatedInput": decision.updated_input}
        if decision.reason:
            body["reason"] = decision.reason
        return _json.dumps(body), 0
    if decision.outcome == ASK:
        return _json.dumps({"decision": "ask", "reason": decision.reason or "confirmation required"}), 0
    if decision.outcome in (DENY, REWRITE):
        reason = decision.reason
        if decision.outcome == REWRITE:
            reason = "%s (no replacement input was supplied)" % (reason or "input requires modification")
        return _json.dumps({"decision": "block", "reason": reason or "blocked by policy"}), 0

    body = {"decision": "allow"}
    if decision.outcome == ALLOW and decision.reason:
        body["additionalContext"] = decision.reason
    return _json.dumps(body), 0


hook_config = make_hook_config(REVERSE_EVENT_MAP)


CONFIG_PATH = "~/.junie/config.json"
