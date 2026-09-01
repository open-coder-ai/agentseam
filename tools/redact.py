"""Reduce a captured hook payload to its shape, discarding everything that could identify."""

from __future__ import annotations

import json as _json

STRUCTURAL_KEYS = frozenset(
    {
        "hook_event_name",
        "hookEventName",
        "hook_name",
        "event",
        "tool_name",
        "toolName",
        "name",
        "client_type",
        "clientType",
        "permission_mode",
        "permissionMode",
        "approval_policy",
        "sandbox_mode",
        "sandbox",
        "source",
        "trigger",
        "reason_type",
        "failure_type",
        "status",
        "terminationReason",
        "termination_reason",
        "origin_kind",
        "kind",
        "type",
        "subagent_type",
        "mcp_server_name",
        "decision",
        "permission",
        "permissionDecision",
        "cursor_version",
        "cursorVersion",
        "version",
    }
)

MAX_ENUM_LEN = 48
_SEPARATORS = ("/", "\\", "@", "\n", " ")

_TOOL_NAME_KEYS = frozenset({"tool_name", "toolName", "name", "mcp_server_name"})
MAX_TOOL_NAME_LEN = 128


def _is_enumlike(value, key=None):
    cap = MAX_TOOL_NAME_LEN if key in _TOOL_NAME_KEYS else MAX_ENUM_LEN
    return isinstance(value, str) and 0 < len(value) <= cap and not any(sep in value for sep in _SEPARATORS)


def _type_of(value):
    if isinstance(value, bool):
        return "<bool>"
    if isinstance(value, int):
        return "<int>"
    if isinstance(value, float):
        return "<float>"
    if value is None:
        return "<null>"
    if isinstance(value, str):
        return "<str:%d>" % len(value)
    return "<%s>" % type(value).__name__


def _embedded_json(value):
    """The parsed object inside a JSON-encoded string, or None."""
    if not isinstance(value, str) or value[:1] not in ("{", "["):
        return None
    try:
        parsed = _json.loads(value)
    except Exception:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def redact(value, key=None):
    """Shape-only copy of `value`. Never returns any string the caller passed in."""
    if isinstance(value, dict):
        return {k: redact(v, key=k) for k, v in value.items()}
    inner = _embedded_json(value)
    if inner is not None:
        return {"<json-string>": redact(inner, key=key)}
    if isinstance(value, list):
        shaped = [redact(v) for v in value[:2]]
        if len(value) > 2:
            shaped.append("<...%d more>" % (len(value) - 2))
        return shaped
    if isinstance(value, bool) or isinstance(value, (int, float)) or value is None:
        return value
    if key in STRUCTURAL_KEYS and _is_enumlike(value, key=key):
        return value
    return _type_of(value)


def keys_of(payload, prefix=""):
    """Every key path in a payload, so two captures can be diffed on structure alone."""
    found = []
    if isinstance(payload, dict):
        for k, v in sorted(payload.items()):
            path = "%s.%s" % (prefix, k) if prefix else k
            found.append(path)
            found.extend(keys_of(v, path))
    elif isinstance(payload, list) and payload:
        found.extend(keys_of(payload[0], "%s[]" % prefix))
    return found
