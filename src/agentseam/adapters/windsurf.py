"""Windsurf (Cascade) adapter."""

from __future__ import annotations

from ..contract import ASK, DENY, POST_TOOL, PRE_TOOL, PROMPT_SUBMIT, REWRITE, STOP, UNKNOWN, Event

AGENT = "windsurf"

EVENT_MAP = {
    "pre_user_prompt": PROMPT_SUBMIT,
    "pre_run_command": PRE_TOOL,
    "pre_mcp_tool_use": PRE_TOOL,
    "post_mcp_tool_use": POST_TOOL,
    "post_cascade_response": STOP,
}
BLOCKING_EVENTS = ("pre_user_prompt", "pre_run_command", "pre_mcp_tool_use")


def claims(raw):
    if not isinstance(raw, dict):
        return False
    if raw.get("hook_event_name") in EVENT_MAP:
        return True
    return "trajectory_id" in raw and isinstance(raw.get("tool_info"), dict)


def _event_name(raw):
    name = raw.get("hook_event_name")
    if name is not None:
        return name
    info = raw.get("tool_info") or {}
    return "pre_run_command" if info.get("command_line") else "pre_user_prompt"


_MCP_EVENTS = ("pre_mcp_tool_use", "post_mcp_tool_use")


def parse(raw):
    name = _event_name(raw)
    info = raw.get("tool_info") or {}
    if name in _MCP_EVENTS:
        tool = "%s/%s" % (info["server"], info["tool"]) if info.get("server") and info.get("tool") else info.get("tool")
    else:
        tool = name
    return Event(
        AGENT,
        EVENT_MAP.get(name, UNKNOWN),
        tool=tool,
        command=info.get("command_line"),
        path=raw.get("path") or info.get("path"),
        output=raw.get("output") or raw.get("result"),
        prompt=raw.get("query") or raw.get("prompt"),
        session_id=raw.get("trajectory_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


DECISION_VOCABULARY = frozenset()


def respond(decision, event):
    """Exit code only: 2 blocks a pre_* hook, everything else allows."""
    vendor_event = _event_name(event.raw) if event.raw else ""
    blocking = vendor_event in BLOCKING_EVENTS
    if decision.outcome in (DENY, ASK, REWRITE):
        if not blocking:
            return "windsurf: flagged after the fact (%s cannot block): %s" % (
                vendor_event,
                decision.reason or "policy violation",
            ), 0
        if decision.outcome == REWRITE:
            reason = "%s (this agent cannot rewrite tool input; blocking instead)" % (
                decision.reason or "input requires modification"
            )
        elif decision.outcome == ASK:
            if decision.evidence.get("degraded_from") == REWRITE:
                reason = "%s (this agent cannot rewrite tool input; blocking instead)" % (
                    decision.reason or "input requires modification"
                )
            else:
                reason = "%s (this agent cannot prompt for confirmation; blocking instead)" % (
                    decision.reason or "confirmation required"
                )
        else:
            reason = decision.reason or "blocked by policy"
        return reason, 2
    return "", 0


REVERSE_EVENT_MAP = {
    PROMPT_SUBMIT: "pre_user_prompt",
    PRE_TOOL: "pre_run_command",
    POST_TOOL: "post_mcp_tool_use",
    STOP: "post_cascade_response",
}


def hook_config(canonical_events, command, matcher=None):
    """{"hooks": {"<event>": [{"command": ...}]}} -- matchers are not supported."""
    hooks = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if name:
            hooks.setdefault(name, []).append({"command": command})
        if ev == PRE_TOOL:
            hooks.setdefault("pre_mcp_tool_use", []).append({"command": command})
    return {"hooks": hooks}


CONFIG_PATH = ".windsurf/hooks.json"
