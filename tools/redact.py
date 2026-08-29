"""Reduce a captured hook payload to its shape, discarding everything that could identify.

The point of a live capture is to learn the *shape* a vendor really sends: which keys exist,
how they nest, what type each value is, and which of the small set of structural enums it
carries. None of that needs the content, and the content is exactly what must not travel --
a payload can hold a prompt, a file being written, a session id, a home directory, an email.

So this keeps keys and types and drops values, with a short allowlist of keys whose *values*
are structural rather than personal. Redaction runs before anything is written to disk, so
the capture file on the machine is already safe; there is no second step to forget.

Deliberately an allowlist. A denylist of "things that look sensitive" fails the first time a
vendor adds a field nobody predicted, and a live capture is exactly where unpredicted fields
turn up.
"""

from __future__ import annotations

import json as _json

#: Keys whose values describe the protocol rather than the user. Everything else is typed.
#:
#: A value is kept only if it is also short and free of separators -- an enum, not prose --
#: so a vendor reusing one of these names for something richer cannot leak through it.
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

#: An allowed value must look like an enum: short, and without the separators that show up in
#: paths, sentences and identifiers carrying data.
MAX_ENUM_LEN = 48
_SEPARATORS = ("/", "\\", "@", "\n", " ")

#: A tool name is an identifier, not prose, but an MCP tool name (`mcp__<server>__<tool>`)
#: routinely runs past MAX_ENUM_LEN -- a capture session gating MCP calls would then lose
#: WHICH tool fired on exactly the surface the matrix most needs verified. These keys get a
#: longer cap; they are still checked for separators, so a value that is actually prose
#: still falls back to a length.
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
        # Length is shape too: it distinguishes an id from a file being written, and no
        # part of a string is reproduced.
        return "<str:%d>" % len(value)
    return "<%s>" % type(value).__name__


def _embedded_json(value):
    """The parsed object inside a JSON-encoded string, or None.

    A vendor may send a whole sub-payload as a *string* rather than an object. VS Code
    Copilot does exactly this: witnessed live 2026-08-29, `Edit` sends `tool_input` as a
    129-character JSON string while `Read` and `Glob` send objects. Treating that string as
    opaque loses the one thing a capture exists to learn -- which keys the write tool
    carries -- and reports it as `<str:129>`, which reads like an id.

    Only dicts and lists are unwrapped. A bare JSON scalar ("42", "true", a quoted string)
    is still just a value and stays a value: json.loads would happily turn a user's typed
    `true` into a bool and claim structure that is not there.
    """
    if not isinstance(value, str) or value[:1] not in ("{", "["):
        return None
    try:
        parsed = _json.loads(value)
    except Exception:
        return None
    return parsed if isinstance(parsed, (dict, list)) else None


def redact(value, key=None):
    """Shape-only copy of `value`. Never returns any string the caller passed in.

    The one exception is a structural key holding an enum-like value, which is the whole
    point of capturing: `hook_event_name` is the field we most need to read back.

    A JSON-encoded string is unwrapped and redacted as the structure it is -- keys kept,
    values shaped, exactly as if the vendor had sent an object. Nothing is loosened by this:
    every leaf still goes through the same allowlist, so the values inside an embedded
    payload are redacted by the identical rules as the values outside it.
    """
    if isinstance(value, dict):
        return {k: redact(v, key=k) for k, v in value.items()}
    inner = _embedded_json(value)
    if inner is not None:
        # Marked, not silently flattened: a reader must be able to tell that the vendor
        # sent a string here, because an adapter parsing this field has to decode it.
        return {"<json-string>": redact(inner, key=key)}
    if isinstance(value, list):
        # Keep the first two entries' shapes; a longer list adds a count, not more shape.
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
