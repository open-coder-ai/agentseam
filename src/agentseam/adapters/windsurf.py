"""Windsurf (Cascade) adapter.

Verified against a real, working Windsurf hook installation: `.windsurf/hooks.json`
plus its hook scripts in PaloAltoNetworks/prisma-airs-integrations. The vendor's own
docs are not reachable from this project's network, so a shipped third-party
integration is the primary source used, and the matrix row says so.

Two properties make this agent unlike the others, and both narrow what a consumer may
promise:

  * Blocking is exit code 2 and nothing else. There is no stdout decision protocol,
    so there is no way to attach a machine-readable reason, and no rewrite.
  * There is NO file-write event. Windsurf exposes prompt, terminal-command and MCP
    hooks; a write to a memory file is not visible to a hook at all. That is a hole
    in coverage, not a gap in this adapter, and the matrix records it as such.
"""

from __future__ import annotations

from ..contract import ASK, DENY, POST_TOOL, PRE_TOOL, PROMPT_SUBMIT, REWRITE, STOP, Event

AGENT = "windsurf"

EVENT_MAP = {
    "pre_user_prompt": PROMPT_SUBMIT,
    "pre_run_command": PRE_TOOL,
    "pre_mcp_tool_use": PRE_TOOL,
    "post_mcp_tool_use": POST_TOOL,
    "post_cascade_response": STOP,
}
# Only the pre_* events can stop anything; the rest are observation.
BLOCKING_EVENTS = ("pre_user_prompt", "pre_run_command", "pre_mcp_tool_use")


def claims(raw):
    if not isinstance(raw, dict):
        return False
    if raw.get("hook_event_name") in EVENT_MAP:
        return True
    # Windsurf's terminal payload nests the command under tool_info and carries a
    # trajectory_id, which no other agent sends.
    return "trajectory_id" in raw and isinstance(raw.get("tool_info"), dict)


def parse(raw):
    name = raw.get("hook_event_name")
    if name not in EVENT_MAP:
        # Infer from payload shape when the event name is absent: a command means the
        # terminal hook, otherwise treat it as the prompt hook.
        info = raw.get("tool_info") or {}
        name = "pre_run_command" if info.get("command_line") else "pre_user_prompt"
    info = raw.get("tool_info") or {}
    return Event(
        AGENT,
        EVENT_MAP[name],
        tool=name,
        command=info.get("command_line"),
        path=raw.get("path") or info.get("path"),
        # No file-write hook exists, so `content` is never populated for this agent.
        output=raw.get("output") or raw.get("result"),
        prompt=raw.get("query") or raw.get("prompt"),
        session_id=raw.get("trajectory_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def respond(decision, event):
    """Exit code only: 2 blocks a pre_* hook, everything else allows.

    The reason goes to stderr because that is the only channel Windsurf reads, and a
    blocked action with no explanation is a support ticket waiting to happen.
    """
    vendor_event = event.tool or ""
    blocking = vendor_event in BLOCKING_EVENTS
    if decision.outcome in (DENY, ASK, REWRITE):
        if not blocking:
            # A post_* hook cannot stop anything. Say that plainly rather than
            # returning 2 and implying the action was prevented.
            return "windsurf: flagged after the fact (%s cannot block): %s" % (
                vendor_event,
                decision.reason or "policy violation",
            ), 0
        if decision.outcome == REWRITE:
            reason = "%s (this agent cannot rewrite tool input; blocking instead)" % (
                decision.reason or "input requires modification"
            )
        elif decision.outcome == ASK:
            # A rewrite reduced to ask upstream is still, to the user, a rewrite that
            # could not happen. Report the original cause, not the intermediate one.
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


def hook_config(canonical_events, command, matcher=None):
    """{"hooks": {"<event>": [{"command": ...}]}} -- matchers are not supported."""
    reverse = {
        PROMPT_SUBMIT: "pre_user_prompt",
        PRE_TOOL: "pre_run_command",
        POST_TOOL: "post_mcp_tool_use",
        STOP: "post_cascade_response",
    }
    hooks = {}
    for ev in canonical_events:
        name = reverse.get(ev)
        if name:
            hooks.setdefault(name, []).append({"command": command})
    return {"hooks": hooks}


CONFIG_PATH = ".windsurf/hooks.json"
