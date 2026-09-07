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
from ._hook_json import _ESCALATE_FROM_TRANSFORM, _TRANSFORM_MISSING_INPUT
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
    """The wire name to answer at -- `cursor_wire` again, so respond and parse cannot diverge.

    `tool` is read only for an Event carrying no payload, where `parse` left the inferred
    name there; without a payload there is nothing to re-infer from.
    """
    name = (event.raw or {}).get("hook_event_name")
    if name in cfg["events"]:
        return name
    if event.raw:
        return cursor_wire(event.raw)
    return event.tool if event.tool in cfg["events"] else cfg["verdicts"].get("default_wire_event")


def _flag_payload(v, decision, name):
    """POST_TOOL/TOOL_FAILURE: a flag can only be raised as additional context, never blocked."""
    if decision.outcome not in (DENY, ESCALATE):
        return "", 0
    note = v["flag_note"] % (name, decision.reason or v["flag_note_default"])
    return _json.dumps({"additional_context": note}), 0


def _prompt_submit_payload(decision):
    payload = {"continue": decision.outcome not in (DENY, ESCALATE, TRANSFORM)}
    if decision.reason:
        payload["user_message"] = decision.reason
    return _json.dumps(payload), 0


def _refusal_reason(v, gate, decision, name):
    """The handler's own reason, plus why the outcome changed shape on the way out."""
    notes = v["degrade_notes"]
    if decision.outcome == TRANSFORM:
        # A gate that DOES honour transform refused only for want of a replacement input;
        # "this gate cannot express it" would be false at the one gate that can.
        key = _TRANSFORM_MISSING_INPUT if gate["honours_transform"] else "transform"
        return _because(decision.reason, notes[key])
    if decision.outcome == ESCALATE:
        note = notes[_ESCALATE_FROM_TRANSFORM] if degraded_from(decision) == TRANSFORM else notes["escalate"]
        return _because(decision.reason, note % name)
    return decision.reason


def _gate_payload(v, gate, decision, name):
    """The PRE_TOOL gate's (permission, reason) pair, before the shared trailing message rule."""
    words = v["words"]
    if decision.outcome == TRANSFORM and gate["honours_transform"] and decision.updated_input is not None:
        return {"permission": words["allow"], "updated_input": decision.updated_input}, decision.reason
    if decision.outcome == ESCALATE and gate["honours_escalate"]:
        return {"permission": words["escalate"]}, decision.reason
    if decision.outcome in (DENY, ESCALATE, TRANSFORM):
        return {"permission": words["block"]}, _refusal_reason(v, gate, decision, name)
    return {"permission": words["allow"]}, decision.reason


def cursor_respond(cfg, decision, event):
    v = cfg["verdicts"]
    name = _wire_of(cfg, event)
    canonical = cfg["events"].get(name)

    if canonical == FILE_CHANGED:
        return "", 0
    if canonical in (POST_TOOL, TOOL_FAILURE):
        return _flag_payload(v, decision, name)
    if canonical == PROMPT_SUBMIT:
        return _prompt_submit_payload(decision)

    gate = v["gates"].get(name)
    if gate is None or canonical != PRE_TOOL:
        return "", 0

    payload, reason = _gate_payload(v, gate, decision, name)
    if reason and payload["permission"] != v["words"]["allow"]:
        payload["user_message"] = reason
        payload["agent_message"] = reason
    return _json.dumps(payload), 0
