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


def _is_enumlike(value):
    return isinstance(value, str) and 0 < len(value) <= MAX_ENUM_LEN and not any(sep in value for sep in _SEPARATORS)


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


def redact(value, key=None):
    """Shape-only copy of `value`. Never returns any string the caller passed in.

    The one exception is a structural key holding an enum-like value, which is the whole
    point of capturing: `hook_event_name` is the field we most need to read back.
    """
    if isinstance(value, dict):
        return {k: redact(v, key=k) for k, v in value.items()}
    if isinstance(value, list):
        # Keep the first two entries' shapes; a longer list adds a count, not more shape.
        shaped = [redact(v) for v in value[:2]]
        if len(value) > 2:
            shaped.append("<...%d more>" % (len(value) - 2))
        return shaped
    if isinstance(value, bool) or isinstance(value, (int, float)) or value is None:
        return value
    if key in STRUCTURAL_KEYS and _is_enumlike(value):
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
