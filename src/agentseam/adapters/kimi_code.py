"""Kimi Code CLI adapter."""

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

AGENT = "kimi_code"

CLIENT_TYPE = "kimi_code_cli"

EVENT_MAP = {
    "UserPromptSubmit": PROMPT_SUBMIT,
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "PostToolUseFailure": TOOL_FAILURE,
    "PermissionResult": POST_TOOL,
    "Stop": STOP,
    "UserPromptQueued": UNKNOWN,
    "PermissionRequest": UNKNOWN,
    "StopFailure": UNKNOWN,
    "Interrupt": UNKNOWN,
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "SubagentStart": SUBAGENT_START,
    "SubagentStop": SUBAGENT_STOP,
    "PreCompact": PRE_COMPACT,
    "PostCompact": PRE_COMPACT,
}
REVERSE_EVENT_MAP = {
    PROMPT_SUBMIT: "UserPromptSubmit",
    PRE_TOOL: "PreToolUse",
    POST_TOOL: "PostToolUse",
    TOOL_FAILURE: "PostToolUseFailure",
    STOP: "Stop",
    SESSION_START: "SessionStart",
    SESSION_END: "SessionEnd",
    SUBAGENT_START: "SubagentStart",
    SUBAGENT_STOP: "SubagentStop",
    PRE_COMPACT: "PreCompact",
}

BLOCKING_EVENTS = ("PreToolUse", "UserPromptSubmit", "Stop")


def claims(raw):
    if not isinstance(raw, dict):
        return False
    return raw.get("client_type") == CLIENT_TYPE and raw.get("hook_event_name") in EVENT_MAP


def parse(raw):
    ti = raw.get("tool_input")
    ti = tool_input_of(ti)
    content = ti.get("content") or ti.get("new_string") or ti.get("new_source") or None
    if content is None and isinstance(ti.get("edits"), list):
        joined = "\n".join(str(e.get("new_string", "")) for e in ti["edits"] if isinstance(e, dict))
        content = joined or None
    out = raw.get("tool_output")
    if isinstance(out, (dict, list)):
        out = _json.dumps(out)
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
        tool=raw.get("tool_name"),
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("path") or ti.get("notebook_path"),
        content=content,
        output=out,
        prompt=raw.get("prompt"),
        session_id=raw.get("session_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def _because(reason, note):
    return "%s (%s)" % (reason, note) if reason else note


DECISION_VOCABULARY = frozenset({"allow", "deny", "ask"})


def respond(decision, event):
    name = (event.raw or {}).get("hook_event_name")
    if name not in BLOCKING_EVENTS:
        return "", 0

    reason = decision.reason
    if decision.outcome == REWRITE:
        reason = _because(reason, "Kimi Code cannot modify a tool call")
    elif decision.outcome == ASK:
        note = (
            "Kimi Code cannot modify a tool call"
            if degraded_from(decision) == REWRITE
            else "Kimi Code cannot prompt for confirmation"
        )
        reason = _because(reason, note)
    elif decision.outcome != DENY:
        return "", 0

    body = {
        "hookEventName": name,
        "permissionDecision": "deny",
        "permissionDecisionReason": reason or "blocked by policy",
    }
    return _json.dumps({"hookSpecificOutput": body}), 0


CONFIG_PATH = "~/.kimi-code/config.toml"

CONFIG_FORMAT = "toml"


def hook_config(canonical_events, command, matcher=None):
    """The `[[hooks]]` entries, as data. `render_config` turns them into TOML text."""
    rules = []
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        rule = {"event": name, "command": command}
        if matcher:
            rule["matcher"] = matcher
        rules.append(rule)
    return rules


def _toml_value(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % escaped


def render_config(rules):
    """Emit `[[hooks]]` tables. Only the four documented fields, in a documented order."""
    blocks = []
    for rule in rules:
        lines = ["[[hooks]]"]
        for key in ("event", "matcher", "command", "timeout"):
            if rule.get(key) is not None:
                lines.append("%s = %s" % (key, _toml_value(rule[key])))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"
