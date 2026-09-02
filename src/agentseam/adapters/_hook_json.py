"""The F1 `hook_json` / F2 `flat_decision` engine: respond rendering for a vendor config entry.

Every function takes the vendor's `data/vendors/<agent>.json` entry as its first argument;
`_family.bind()` closes them over one entry (with `_payload.py`'s claims/parse side), and a
bundle inlines both modules next to a `VENDOR` literal. What varies per vendor is only the
data the entry carries (dialect-families.md §3.1: words, key chains, flags, note strings);
the shapes rendered here are the family's G1/G2 grammars and the shared
`hookSpecificOutput` context/transform bodies.
"""

from __future__ import annotations

import json as _json

from ..contract import ALLOW, DENY, ESCALATE, TRANSFORM, UNKNOWN, VOUCH, WARN, degraded_from
from ._payload import _wire_name


#: `degrade_notes` keys named more than once below; kept as constants rather than repeated
#: literals (they are also part of the vendor entry's own `degrade_notes` schema).
_ESCALATE_FROM_TRANSFORM = "escalate_from_transform"
_TRANSFORM_MISSING_INPUT = "transform_missing_input"


def hj_reverse(cfg):
    """Canonical event -> wire name: the naive inverse, then the entry's pinned overrides."""
    reverse = {}
    for name, canonical in cfg["events"].items():
        if canonical != UNKNOWN:
            reverse[canonical] = name
    reverse.update(cfg.get("wire_events", {}))
    return reverse


def _context_value(v, decision):
    if v.get("context_source") == "context":
        return decision.context
    if v.get("context_source") == "reason":
        return decision.reason
    return None


def _context_body(name, value):
    return _json.dumps({"hookSpecificOutput": {"hookEventName": name, "additionalContext": value}}), 0


def _note_for(v, decision, at_gate, missing_input):
    notes = v.get("degrade_notes", {})
    if decision.outcome == ESCALATE:
        if degraded_from(decision) == TRANSFORM and _ESCALATE_FROM_TRANSFORM in notes:
            return notes[_ESCALATE_FROM_TRANSFORM]
        if at_gate and "escalate_gate" in notes:
            return notes["escalate_gate"]
        return notes.get("escalate")
    if decision.outcome == TRANSFORM:
        if missing_input and _TRANSFORM_MISSING_INPUT in notes:
            return notes[_TRANSFORM_MISSING_INPUT]
        return notes.get("transform")
    return None


def _default_for(v, decision, at_gate, wire=None):
    gate_defaults = v.get("gate_reason_defaults", {})
    if wire in gate_defaults:
        return gate_defaults[wire]
    defaults = v.get("reason_defaults", {})
    key = {DENY: "deny", ESCALATE: "escalate", TRANSFORM: "transform"}.get(decision.outcome, "deny")
    if at_gate and key + "_gate" in defaults:
        return defaults[key + "_gate"]
    return defaults.get(key, "blocked by policy")


def _refusal_text(v, decision, at_gate, wire=None):
    note = _note_for(v, decision, at_gate, decision.updated_input is None)
    default = _default_for(v, decision, at_gate, wire)
    if note and "%s" in note:
        # A template note fills (the reason or its default, the wire event name) itself.
        return note % (decision.reason or default, wire)
    reason = decision.reason
    if v.get("note_style") == "suffix":
        reason = reason or default
        return "%s (%s)" % (reason, note) if note else reason
    text = "%s (%s)" % (reason, note) if reason and note else (note or reason)
    return text or default


def _g1(v, gate, decision, wire, name):
    """Block dialect: a top-level decision word, or silence/context where nothing is read."""
    words = dict(v.get("words", {}))
    words.update(v.get("words_at", {}).get(wire, {}))
    at_context_event = wire in v.get("context_events", ())
    if decision.outcome in (ALLOW, VOUCH, WARN):
        value = _context_value(v, decision)
        if at_context_event and value:
            return _context_body(name, value)
        if wire in v.get("allow_silent_events", ()):
            return "", 0
        if "allow" in words:
            out = {"decision": words["allow"]}
            if v.get("allow_context_key") and decision.outcome == ALLOW and value:
                out[v["allow_context_key"]] = value
            return _json.dumps(out), 0
        return "", 0
    if decision.outcome == TRANSFORM and gate["honours_transform"]:
        if v.get("transform_grammar") == "hook_specific_tool_input":
            return _json.dumps({"hookSpecificOutput": {"tool_input": decision.updated_input}}), 0
        if decision.updated_input is not None:
            if v.get("transform_grammar") == "top_level_updated_input":
                out = {"decision": words.get("transform", "allow"), "updatedInput": decision.updated_input}
                if decision.reason:
                    out["reason"] = decision.reason
                return _json.dumps(out), 0
            return _json.dumps(
                {"hookSpecificOutput": {"hookEventName": name, "updatedInput": decision.updated_input}}
            ), 0
    if (
        decision.outcome == ESCALATE
        and gate["honours_escalate"]
        and "escalate" in words
        # An escalate the dispatcher degraded a transform into is a block where the entry
        # names that degradation (antigravity): prompting would offer the unmodified call.
        and not (degraded_from(decision) == TRANSFORM and _ESCALATE_FROM_TRANSFORM in v.get("degrade_notes", {}))
    ):
        reason = decision.reason or _default_for(v, decision, True, wire)
        return _json.dumps({"decision": words["escalate"], "reason": reason}), 0
    out = {"decision": words.get("block", "block"), "reason": _refusal_text(v, decision, False, wire)}
    if at_context_event and v.get("context_source") == "context" and decision.context:
        out["hookSpecificOutput"] = {"hookEventName": name, "additionalContext": decision.context}
    return _json.dumps(out), 0


#: The G2 dialect's one reason field, named four times below.
_PERMISSION_DECISION_REASON = "permissionDecisionReason"


def _g2(v, gate, decision, name):
    """Permission gate: `hookSpecificOutput.permissionDecision`, filled from the word table."""
    if decision.outcome in (ALLOW, WARN):
        return "", 0
    words = v.get("words", {})
    out = {"hookEventName": name}
    if decision.outcome == VOUCH:
        if "vouch" not in words:
            return "", 0
        out["permissionDecision"] = words["vouch"]
        if decision.reason:
            out[_PERMISSION_DECISION_REASON] = decision.reason
    elif (
        decision.outcome == TRANSFORM
        and gate["honours_transform"]
        and not (decision.updated_input is None and _TRANSFORM_MISSING_INPUT in v.get("degrade_notes", {}))
    ):
        out["permissionDecision"] = words.get("transform", "allow")
        out["updatedInput"] = decision.updated_input
        if decision.reason:
            out[_PERMISSION_DECISION_REASON] = decision.reason
    elif decision.outcome == ESCALATE and gate["honours_escalate"] and "escalate" in words:
        out["permissionDecision"] = words["escalate"]
        out[_PERMISSION_DECISION_REASON] = decision.reason or _default_for(v, decision, True)
    else:
        out["permissionDecision"] = words.get("deny", "deny")
        out[_PERMISSION_DECISION_REASON] = _refusal_text(v, decision, True)
    return _json.dumps({"hookSpecificOutput": out}), 0


def hj_respond(cfg, decision, event, wire=None):
    """(stdout_text, exit_code) in this entry's dialect for the gate the payload names.

    `wire` is the pre-resolved wire event name for the shape-inferred families; the
    marker families resolve it from the payload's own event key.
    """
    v = cfg["verdicts"]
    if wire is None:
        wire = _wire_name(cfg, event.raw or {})
    if wire in v.get("empty_object_events", ()):
        return _json.dumps({}), 0
    if wire is None:
        wire = v.get("default_wire_event")
        if wire is None and v.get("missing_wire") == "reverse_map":
            wire = hj_reverse(cfg).get(event.event)
    name = wire if v.get("echo") == "payload" else hj_reverse(cfg).get(event.event, "PreToolUse")
    gate = v["gates"].get(wire)
    if gate is None:
        value = _context_value(v, decision)
        if wire in v.get("context_events", ()) and value:
            return _context_body(name, value)
        return "", 0
    if gate["grammar"] == "G2":
        return _g2(v, gate, decision, name)
    return _g1(v, gate, decision, wire, name)
