"""The F4 `windsurf` family: shape-inferred claims and the G5 exit-code dialect.

Shape inference stays code (dialect-families.md §3.3); the note strings and blocking
gates come from the vendor's `data/vendors/windsurf.json` entry.
"""

from __future__ import annotations

from ..contract import DENY, ESCALATE, TRANSFORM
from ._hook_json import _refusal_text
from ._payload import hj_parse, wire_name_of

_MCP_EVENTS = ("pre_mcp_tool_use", "post_mcp_tool_use")


def _tool_info(raw):
    info = raw.get("tool_info") if isinstance(raw, dict) else None
    return info if isinstance(info, dict) else {}


def _named(cfg, raw):
    for key in cfg["claims"]["event_key"]:
        name = wire_name_of(raw, key)
        if name is not None:
            return name
    return None


def windsurf_wire(cfg, raw):
    """The wire event name, inferred from `tool_info` when the payload names none."""
    name = _named(cfg, raw)
    if name is not None or not isinstance(raw, dict):
        return name
    return "pre_run_command" if _tool_info(raw).get("command_line") else "pre_user_prompt"


def windsurf_claims(cfg, raw):
    if not isinstance(raw, dict):
        return False
    if _named(cfg, raw) in cfg["events"]:
        return True
    return "trajectory_id" in raw and isinstance(raw.get("tool_info"), dict)


def windsurf_parse(cfg, raw):
    name = windsurf_wire(cfg, raw)
    event = hj_parse(cfg, raw, wire=name)
    info = _tool_info(raw)
    if name in _MCP_EVENTS:
        server = info.get("mcp_server_name") or info.get("server")
        tool = info.get("mcp_tool_name") or info.get("tool")
        event.tool = "%s/%s" % (server, tool) if server and tool else tool
    else:
        event.tool = name
    return event


def windsurf_respond(cfg, decision, event):
    """Exit code only: 2 blocks at a gate; elsewhere a refusal can only be flagged."""
    v = cfg["verdicts"]
    if decision.outcome not in (DENY, ESCALATE, TRANSFORM):
        return "", 0
    wire = windsurf_wire(cfg, event.raw) if event.raw else ""
    if wire not in v["gates"]:
        return v["flag_note"] % (wire, decision.reason or v["flag_note_default"]), 0
    return _refusal_text(v, decision, at_gate=False, wire=wire), 2
