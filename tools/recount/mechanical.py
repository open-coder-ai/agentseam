"""Module constants, read directly off the imported adapter -- no AST, no execution needed."""

from __future__ import annotations

from agentseam.matrix_data import MATRIX


def mechanical(agent, mod):
    entry = {
        "agent": agent,
        "display": MATRIX[agent]["display"],
        "config_path": mod.CONFIG_PATH,
        "config_format": getattr(mod, "CONFIG_FORMAT", "json"),
        "needs_trust": bool(getattr(mod, "NEEDS_TRUST", False)),
    }
    if hasattr(mod, "EVENT_MAP"):
        entry["events"] = dict(mod.EVENT_MAP)
    else:
        entry["events"] = {}  # antigravity: no wire event name exists to parse (dialect-families.md §1)
    tools = {}
    for key, attr in (("write", "WRITE_TOOLS"), ("shell", "SHELL_TOOLS"), ("memory", "MEMORY_TOOLS")):
        values = getattr(mod, attr, ())
        if values:
            tools[key] = list(values)
    entry["tools"] = tools
    return entry


def wire_events(mod):
    """Canonical events where `REVERSE_EVENT_MAP` picks something other than the naive inverse.

    The naive inverse of `EVENT_MAP` (`{v: k for k, v in EVENT_MAP.items()}`) collapses a
    many-to-one vendor vocabulary to whichever vendor name was defined *last*; several
    adapters hand-write `REVERSE_EVENT_MAP` to pin a different, deliberate emit direction
    (dialect-families.md §3.2: "grok.py:44-55, kimi_code.py:49-60 collapse many-to-one and
    pin the emit direction"). This diff is exactly that pin, computed rather than transcribed.
    """
    reverse = getattr(mod, "REVERSE_EVENT_MAP", {})
    event_map = getattr(mod, "EVENT_MAP", {})
    naive = {}
    for vendor_name, canonical in event_map.items():
        naive[canonical] = vendor_name
    return {canonical: vendor_name for canonical, vendor_name in reverse.items() if naive.get(canonical) != vendor_name}
