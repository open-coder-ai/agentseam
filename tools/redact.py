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

TOOL_INPUT_KEYS = frozenset(
    {"tool_input", "toolInput", "tool_args", "toolArgs", "arguments", "input", "params", "parameters"}
)

#: What the tool returned: file contents and command output, so as private as the arguments are.
TOOL_OUTPUT_KEYS = frozenset(
    {"tool_response", "tool_output", "toolResult", "tool_result", "output", "result", "mcp_result"}
)

_SCHEMA_KEY_LEN = 48


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


def _is_schema_key(key):
    """A key shaped like a field name (an identifier), not like data used as a key (a host, an email, an id)."""
    return isinstance(key, str) and len(key) <= _SCHEMA_KEY_LEN and key.isidentifier()


def redact(value, key=None, *, in_tool_input=False, in_output=False, in_embedded=False):
    """Shape-only copy of `value`. Never returns any string the caller passed in.

    Inside what a tool returned, or JSON text found in a string, a dict key that is not shaped
    like a field name is data and is replaced by its position.
    """
    if isinstance(value, dict):
        keep_all = not (in_output or in_embedded)
        return {
            (k if keep_all or _is_schema_key(k) else "<key:%d>" % i): redact(
                v,
                key=k,
                in_tool_input=in_tool_input or k in TOOL_INPUT_KEYS,
                in_output=in_output or k in TOOL_OUTPUT_KEYS,
                in_embedded=in_embedded,
            )
            for i, (k, v) in enumerate(value.items())
        }
    inner = _embedded_json(value)
    if inner is not None:
        return {
            "<json-string>": redact(
                inner, key=key, in_tool_input=in_tool_input, in_output=in_output, in_embedded=not in_tool_input
            )
        }
    if isinstance(value, list):
        shaped = [
            redact(v, in_tool_input=in_tool_input, in_output=in_output, in_embedded=in_embedded) for v in value[:2]
        ]
        if len(value) > 2:
            shaped.append("<...%d more>" % (len(value) - 2))
        return shaped
    if isinstance(value, bool) or isinstance(value, (int, float)) or value is None:
        return value
    if not (in_tool_input or in_output) and key in STRUCTURAL_KEYS and _is_enumlike(value, key=key):
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
