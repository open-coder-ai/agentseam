"""The F1 `hook_json` family engine: claims/parse/respond driven by a vendor config entry.

Every function takes the vendor's `data/vendors/<agent>.json` entry as its first argument;
`_family.bind()` closes them over one entry, and a bundle inlines this module next to a
`VENDOR` literal. What varies per vendor is only the data the entry carries (dialect-
families.md §3.1: words, key chains, flags, note strings); the shapes rendered here are the
family's G1/G2 grammars and the shared `hookSpecificOutput` context/transform bodies.
"""

from __future__ import annotations

import json as _json

from ..contract import (
    ALLOW,
    DENY,
    ESCALATE,
    TRANSFORM,
    UNKNOWN,
    VOUCH,
    WARN,
    Event,
    degraded_from,
    tool_input_of,
)
from ._probes import PROBES


def hj_reverse(cfg):
    """Canonical event -> wire name: the naive inverse, then the entry's pinned overrides."""
    reverse = {}
    for name, canonical in cfg["events"].items():
        if canonical != UNKNOWN:
            reverse[canonical] = name
    reverse.update(cfg.get("wire_events", {}))
    return reverse


def _wire_name(cfg, raw):
    for key in cfg["claims"].get("event_key", ()):
        name = raw.get(key)
        if name is not None:
            return name
    return None


def hj_claims(cfg, raw):
    """True when this payload matches the entry's marker discipline."""
    if not isinstance(raw, dict):
        return False
    c = cfg["claims"]
    name = _wire_name(cfg, raw)
    if name in c.get("accept_names", ()):
        return True
    if name not in cfg["events"]:
        return False
    if "client_types" in c and raw.get("client_type") not in c["client_types"]:
        return False
    for marker in c.get("reject_markers", ()):
        if marker in raw:
            return False
    for probe, markers in c.get("reject_markers_unless_probe", {}).items():
        if any(marker in raw for marker in markers) and not PROBES[probe](raw):
            return False
    for probe in c.get("reject_probes", ()):
        if PROBES[probe](raw):
            return False
    accept = c.get("accept_markers", ())
    if accept and not any(marker in raw for marker in accept):
        for event_name, required in c.get("accept_when_all", {}).items():
            if name == event_name and all(key in raw for key in required):
                return True
        return False
    return True


def _lookup(raw, ti, key):
    """One dotted key: `tool_input.x` off the decoded tool input, `x[].y` joining a list."""
    if key.startswith("tool_input."):
        rest = key[len("tool_input.") :]
        if "[]." in rest:
            list_key, sub = rest.split("[].", 1)
            items = ti.get(list_key)
            if not isinstance(items, (list, tuple)):
                return None
            joined = "\n".join(str(item.get(sub, "")) for item in items if isinstance(item, dict))
            return joined or None
        return ti.get(rest)
    return raw.get(key)


def _field(raw, ti, chain):
    value = None
    for key in chain:
        if value:
            break
        value = value or _lookup(raw, ti, key)
    return value


def hj_parse(cfg, raw):
    """Normalise one payload along the entry's ordered field-fallback chains."""
    ti = tool_input_of(raw.get("tool_input"))
    fields = {name: _field(raw, ti, chain) for name, chain in cfg["fields"].items()}
    if isinstance(fields.get("output"), (dict, list)):
        fields["output"] = _json.dumps(fields["output"])
    return Event(
        cfg["agent"],
        cfg["events"].get(_wire_name(cfg, raw), UNKNOWN),
        tool=fields.get("tool"),
        command=fields.get("command"),
        path=fields.get("path"),
        content=fields.get("content"),
        output=fields.get("output"),
        prompt=fields.get("prompt"),
        session_id=fields.get("session_id"),
        tool_use_id=fields.get("tool_use_id"),
        cwd=fields.get("cwd"),
        raw=raw,
    )


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
        if degraded_from(decision) == TRANSFORM and "escalate_from_transform" in notes:
            return notes["escalate_from_transform"]
        if at_gate and "escalate_gate" in notes:
            return notes["escalate_gate"]
        return notes.get("escalate")
    if decision.outcome == TRANSFORM:
        if missing_input and "transform_missing_input" in notes:
            return notes["transform_missing_input"]
        return notes.get("transform")
    return None


def _default_for(v, decision, at_gate):
    defaults = v.get("reason_defaults", {})
    key = {DENY: "deny", ESCALATE: "escalate", TRANSFORM: "transform"}.get(decision.outcome, "deny")
    if at_gate and key + "_gate" in defaults:
        return defaults[key + "_gate"]
    return defaults.get(key, "blocked by policy")


def _refusal_text(v, decision, at_gate):
    note = _note_for(v, decision, at_gate, decision.updated_input is None)
    default = _default_for(v, decision, at_gate)
    reason = decision.reason
    if v.get("note_style") == "suffix":
        reason = reason or default
        return "%s (%s)" % (reason, note) if note else reason
    text = "%s (%s)" % (reason, note) if reason and note else (note or reason)
    return text or default


def _g1(v, gate, decision, wire, name):
    """Block dialect: a top-level decision word, or silence/context where nothing is read."""
    words = v.get("words", {})
    at_context_event = wire in v.get("context_events", ())
    if decision.outcome in (ALLOW, VOUCH, WARN):
        value = _context_value(v, decision)
        if at_context_event and value:
            return _context_body(name, value)
        if "allow" in words:
            return _json.dumps({"decision": words["allow"]}), 0
        return "", 0
    if decision.outcome == TRANSFORM and gate["honours_transform"] and decision.updated_input is not None:
        return _json.dumps({"hookSpecificOutput": {"hookEventName": name, "updatedInput": decision.updated_input}}), 0
    out = {"decision": words.get("block", "block"), "reason": _refusal_text(v, decision, False)}
    if at_context_event and v.get("context_source") == "context" and decision.context:
        out["hookSpecificOutput"] = {"hookEventName": name, "additionalContext": decision.context}
    return _json.dumps(out), 0


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
            out["permissionDecisionReason"] = decision.reason
    elif (
        decision.outcome == TRANSFORM
        and gate["honours_transform"]
        and not (decision.updated_input is None and "transform_missing_input" in v.get("degrade_notes", {}))
    ):
        out["permissionDecision"] = words.get("transform", "allow")
        out["updatedInput"] = decision.updated_input
        if decision.reason:
            out["permissionDecisionReason"] = decision.reason
    elif decision.outcome == ESCALATE and gate["honours_escalate"] and "escalate" in words:
        out["permissionDecision"] = words["escalate"]
        out["permissionDecisionReason"] = decision.reason or _default_for(v, decision, True)
    else:
        out["permissionDecision"] = words.get("deny", "deny")
        out["permissionDecisionReason"] = _refusal_text(v, decision, True)
    return _json.dumps({"hookSpecificOutput": out}), 0


def hj_respond(cfg, decision, event):
    """(stdout_text, exit_code) in this entry's dialect for the gate the payload names."""
    v = cfg["verdicts"]
    wire = _wire_name(cfg, event.raw or {})
    if wire is None:
        wire = v.get("default_wire_event")
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
