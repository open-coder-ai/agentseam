"""The engine's payload side: marker claims and chain-driven parse for one config entry.

Split from `_hook_json.py` by activity (the 300-line budget): this module reads what a
vendor sent -- `hj_claims` over the entry's marker discipline, `hj_parse` down its ordered
field-fallback chains -- and `_hook_json.py` renders what we say back.
"""

from __future__ import annotations

import json as _json

from ..contract import UNKNOWN, Event, tool_input_of
from ._probes import PROBES


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


def _segment(node, part):
    """One path segment: a dict key, or `key[N]` indexing the list under it."""
    if part.endswith("]") and "[" in part:
        key, _, index = part[:-1].partition("[")
        items = node.get(key) if isinstance(node, dict) else None
        i = int(index)
        return items[i] if isinstance(items, (list, tuple)) and len(items) > i else None
    return node.get(part) if isinstance(node, dict) else None


def _walk(node, path):
    """A dotted path off `node`; `a[].b` joins `b` over `a`'s dict items, `a[0]` indexes."""
    if "[]." in path:
        head, sub = path.split("[].", 1)
        items = _walk(node, head)
        if not isinstance(items, (list, tuple)):
            return None
        joined = "\n".join(str(item.get(sub, "")) for item in items if isinstance(item, dict))
        return joined or None
    for part in path.split("."):
        node = _segment(node, part)
        if node is None:
            return None
    return node


def _lookup(raw, ti, key):
    """One config key: a `tool_input.` path walks the decoded tool input, else the payload."""
    if key.startswith("tool_input."):
        return _walk(ti, key[len("tool_input.") :])
    return _walk(raw, key)


def _field(raw, ti, chain):
    value = None
    for key in chain:
        if value:
            break
        value = value or _lookup(raw, ti, key)
    return value


#: `fields` keys that steer the extraction rather than naming an Event field.
_FIELD_META = ("tool_input", "content_only_for_write_tools", "stringify")


def _tool_input_raw(cfg, raw):
    for key in cfg["fields"].get("tool_input", ("tool_input",)):
        value = raw.get(key)
        if value is not None:
            return value
    return None


def _canonical_of(cfg, name):
    """The canonical event for one wire name; an entry with no `events` at all (antigravity,
    whose payloads never carry one) maps the shape-inferred name back through `wire_events`."""
    events = cfg["events"]
    if not events:
        return {wire: canonical for canonical, wire in cfg.get("wire_events", {}).items()}.get(name, UNKNOWN)
    return events.get(name, UNKNOWN)


def hj_parse(cfg, raw, wire=None):
    """Normalise one payload along the entry's ordered field-fallback chains.

    `wire` is the pre-resolved wire event name for the shape-inferred families; the
    marker families resolve it from the payload's own event key.
    """
    ti = tool_input_of(_tool_input_raw(cfg, raw))
    fields = {name: _field(raw, ti, chain) for name, chain in cfg["fields"].items() if name not in _FIELD_META}
    if cfg["fields"].get("content_only_for_write_tools") and fields.get("tool") not in cfg["tools"].get("write", ()):
        fields["content"] = None
    if isinstance(fields.get("output"), (dict, list)):
        fields["output"] = _json.dumps(fields["output"])
    for name in cfg["fields"].get("stringify", ()):
        if fields.get(name) is not None:
            fields[name] = str(fields[name])
    return Event(
        cfg["agent"],
        _canonical_of(cfg, wire if wire is not None else _wire_name(cfg, raw)),
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
