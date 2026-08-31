"""Cursor adapter."""

from __future__ import annotations

import json as _json

from ..contract import (
    ASK,
    DENY,
    FILE_CHANGED,
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

AGENT = "cursor"

EVENT_MAP = {
    "sessionStart": SESSION_START,
    "sessionEnd": SESSION_END,
    "preToolUse": PRE_TOOL,
    "postToolUse": POST_TOOL,
    "postToolUseFailure": TOOL_FAILURE,
    "subagentStart": SUBAGENT_START,
    "subagentStop": SUBAGENT_STOP,
    "beforeShellExecution": PRE_TOOL,
    "afterShellExecution": POST_TOOL,
    "beforeMCPExecution": PRE_TOOL,
    "afterMCPExecution": POST_TOOL,
    "beforeReadFile": PRE_TOOL,
    "afterFileEdit": FILE_CHANGED,
    "beforeSubmitPrompt": PROMPT_SUBMIT,
    "preCompact": PRE_COMPACT,
    "stop": STOP,
    "beforeTabFileRead": PRE_TOOL,
    "afterTabFileEdit": FILE_CHANGED,
}

_PERMISSION_GATES = {
    "preToolUse": False,
    "beforeShellExecution": True,
    "beforeMCPExecution": True,
    "beforeReadFile": False,
    "beforeTabFileRead": False,
}

_GATES = frozenset(_PERMISSION_GATES) | {"beforeSubmitPrompt"}

_POST_HOC = (
    "postToolUse",
    "postToolUseFailure",
    "afterShellExecution",
    "afterMCPExecution",
    "afterFileEdit",
    "afterTabFileEdit",
)

_MUTE = ("afterFileEdit", "afterTabFileEdit")


_CURSOR_MARKERS = ("conversation_id", "generation_id", "cursor_version", "workspace_roots")

_AMBIGUOUS_NAMES = (
    "preToolUse",
    "postToolUse",
    "sessionStart",
    "sessionEnd",
    "preCompact",
    "stop",
    "subagentStart",
    "subagentStop",
)


def claims(raw):
    """True when this payload looks like Cursor's shape."""
    if not isinstance(raw, dict):
        return False
    name = raw.get("hook_event_name")
    if name in EVENT_MAP:
        if name in _AMBIGUOUS_NAMES:
            return any(k in raw for k in _CURSOR_MARKERS)
        return True
    if isinstance(raw.get("command"), str) and ("sandbox" in raw or "cwd" in raw) and "tool_input" not in raw:
        return True
    return "file_path" in raw and isinstance(raw.get("edits"), list) and "tool_name" not in raw


def _content_of(raw):
    edits = raw.get("edits")
    if isinstance(edits, list):
        return "\n".join(str(e.get("new_string", "")) for e in edits) or None
    ti = raw.get("tool_input")
    if isinstance(ti, dict):
        return ti.get("content") or ti.get("new_string") or None
    content = raw.get("content")
    return content if isinstance(content, str) and content else None


def parse(raw):
    name = raw.get("hook_event_name")
    if name is None:
        name = "afterFileEdit" if isinstance(raw.get("edits"), list) else "beforeShellExecution"
    ti = raw.get("tool_input")
    ti = tool_input_of(ti)
    command = raw.get("command") or ti.get("command")
    path = raw.get("file_path") or ti.get("file_path") or ti.get("path")
    return Event(
        AGENT,
        EVENT_MAP.get(name, UNKNOWN),
        tool=raw.get("tool_name") or name,
        command=command,
        path=path,
        content=_content_of(raw),
        output=raw.get("tool_output") or raw.get("output") or raw.get("result_json"),
        prompt=raw.get("prompt"),
        session_id=raw.get("conversation_id"),
        tool_use_id=raw.get("tool_use_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def _because(reason, note):
    """Keep the handler's own reason and add why the outcome changed shape."""
    return "%s (%s)" % (reason, note) if reason else note


def _vendor_event(event):
    """The vendor event name, which `parse` keeps in `tool` when the tool has no name."""
    name = (event.raw or {}).get("hook_event_name")
    return name if name in EVENT_MAP else (event.tool if event.tool in EVENT_MAP else "beforeShellExecution")


DECISION_VOCABULARY = frozenset({"allow", "deny", "ask"})


def respond(decision, event):
    name = _vendor_event(event)

    if name in _MUTE:
        return "", 0

    if name in _POST_HOC:
        if decision.outcome in (DENY, ASK):
            note = "observed after the fact (%s cannot prevent it): %s" % (name, decision.reason or "policy violation")
            return _json.dumps({"additional_context": note}), 0
        return "", 0

    if name == "beforeSubmitPrompt":
        payload = {"continue": decision.outcome not in (DENY, ASK, REWRITE)}
        if decision.reason:
            payload["user_message"] = decision.reason
        return _json.dumps(payload), 0

    if name not in _PERMISSION_GATES:
        return "", 0

    honours_ask = _PERMISSION_GATES[name]
    payload = {}
    reason = decision.reason

    if decision.outcome == REWRITE:
        if name == "preToolUse" and decision.updated_input is not None:
            payload = {"permission": "allow", "updated_input": decision.updated_input}
        else:
            payload = {"permission": "deny"}
            reason = _because(reason, "input requires modification, which this gate cannot express")
    elif decision.outcome == DENY:
        payload = {"permission": "deny"}
    elif decision.outcome == ASK:
        if honours_ask:
            payload = {"permission": "ask"}
        else:
            payload = {"permission": "deny"}
            note = (
                "%s cannot modify a tool call" % name
                if degraded_from(decision) == REWRITE
                else "%s cannot prompt for confirmation" % name
            )
            reason = _because(reason, "%s, so this is a block" % note)
    else:
        payload = {"permission": "allow"}

    if reason and payload.get("permission") != "allow":
        payload["user_message"] = reason
        payload["agent_message"] = reason
    return _json.dumps(payload), 0


REVERSE_EVENT_MAP = {
    PRE_TOOL: "preToolUse",
    POST_TOOL: "postToolUse",
    TOOL_FAILURE: "postToolUseFailure",
    PROMPT_SUBMIT: "beforeSubmitPrompt",
    SESSION_START: "sessionStart",
    SESSION_END: "sessionEnd",
    SUBAGENT_START: "subagentStart",
    SUBAGENT_STOP: "subagentStop",
    STOP: "stop",
    PRE_COMPACT: "preCompact",
    FILE_CHANGED: "afterFileEdit",
}


def hook_config(canonical_events, command, matcher=None, fail_closed=True):
    hooks = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        entry = {"command": command}
        if fail_closed and name in _GATES:
            entry["failClosed"] = True
        hooks.setdefault(name, []).append(entry)
    return {"version": 1, "hooks": hooks}


CONFIG_PATH = ".cursor/hooks.json"
