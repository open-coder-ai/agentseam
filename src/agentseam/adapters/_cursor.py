"""The F3 `cursor` family: shape-inferred claims and the G4 permission-object dialect.

Shape inference stays code (dialect-families.md §3.3); everything word- or chain-shaped
comes from the vendor's `data/vendors/cursor.json` entry.
"""

from __future__ import annotations

import json as _json

from ..contract import (
    DENY,
    ESCALATE,
    FILE_CHANGED,
    POST_TOOL,
    PRE_TOOL,
    PROMPT_SUBMIT,
    TOOL_FAILURE,
    TRANSFORM,
    degraded_from,
)
from ._hook_json import _ESCALATE_FROM_TRANSFORM
from ._payload import hj_parse

#: Wire names other vendors also spell this way; a payload naming one is claimed only on
#: Cursor's own base-schema envelope markers.
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

_MARKERS = ("conversation_id", "generation_id", "cursor_version", "workspace_roots")


def cursor_wire(raw):
    """The wire event name, inferred from shape when the payload names none."""
    name = raw.get("hook_event_name")
    if name is None:
        return "afterFileEdit" if isinstance(raw.get("edits"), list) else "beforeShellExecution"
    return name


def cursor_claims(cfg, raw):
    """True when this payload looks like Cursor's shape."""
    if not isinstance(raw, dict):
        return False
    name = raw.get("hook_event_name")
    if name in cfg["events"]:
        if name in _AMBIGUOUS_NAMES:
            return any(k in raw for k in _MARKERS)
        return True
    if isinstance(raw.get("command"), str) and ("sandbox" in raw or "cwd" in raw) and "tool_input" not in raw:
        return True
    return "file_path" in raw and isinstance(raw.get("edits"), list) and "tool_name" not in raw


def cursor_parse(cfg, raw):
    name = cursor_wire(raw)
    event = hj_parse(cfg, raw, wire=name)
    event.tool = event.tool or name
    return event


def _because(reason, note):
    """Keep the handler's own reason and add why the outcome changed shape."""
    return "%s (%s)" % (reason, note) if reason else note


def _wire_of(cfg, event):
    """The wire name to answer at: the payload's own, `tool` where `parse` kept it there,
    else the entry's default gate."""
    name = (event.raw or {}).get("hook_event_name")
    if name in cfg["events"]:
        return name
    return event.tool if event.tool in cfg["events"] else cfg["verdicts"].get("default_wire_event")


def cursor_respond(cfg, decision, event):
    v = cfg["verdicts"]
    name = _wire_of(cfg, event)
    canonical = cfg["events"].get(name)

    if canonical == FILE_CHANGED:
        return "", 0

    if canonical in (POST_TOOL, TOOL_FAILURE):
        if decision.outcome in (DENY, ESCALATE):
            note = v["flag_note"] % (name, decision.reason or v["flag_note_default"])
            return _json.dumps({"additional_context": note}), 0
        return "", 0

    if canonical == PROMPT_SUBMIT:
        payload = {"continue": decision.outcome not in (DENY, ESCALATE, TRANSFORM)}
        if decision.reason:
            payload["user_message"] = decision.reason
        return _json.dumps(payload), 0

    gate = v["gates"].get(name)
    if gate is None or canonical != PRE_TOOL:
        return "", 0

    words = v["words"]
    notes = v["degrade_notes"]
    reason = decision.reason

    if decision.outcome == TRANSFORM:
        if gate["honours_transform"] and decision.updated_input is not None:
            payload = {"permission": words["allow"], "updated_input": decision.updated_input}
        else:
            payload = {"permission": words["block"]}
            reason = _because(reason, notes["transform"])
    elif decision.outcome == DENY:
        payload = {"permission": words["block"]}
    elif decision.outcome == ESCALATE:
        if gate["honours_escalate"]:
            payload = {"permission": words["escalate"]}
        else:
            note = notes[_ESCALATE_FROM_TRANSFORM] if degraded_from(decision) == TRANSFORM else notes["escalate"]
            payload = {"permission": words["block"]}
            reason = _because(reason, note % name)
    else:
        payload = {"permission": words["allow"]}

    if reason and payload["permission"] != words["allow"]:
        payload["user_message"] = reason
        payload["agent_message"] = reason
    return _json.dumps(payload), 0
