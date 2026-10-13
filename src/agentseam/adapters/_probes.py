"""Named payload probes the vendor config may cite (dialect-families.md §3.2, §7)."""

from __future__ import annotations

OBSERVED_MARKERS = (
    "transcript_path",
    "permission_mode",
    "stop_hook_active",
    "agent_transcript_path",
    "background_tasks",
    "session_crons",
    "custom_instructions",
    "effort",
)

#: Claude Code spells an MCP tool `mcp__<server>__<tool>`; Kiro's hook payloads carry the
#: sanitized `mcp_<server>_<tool>` (kiro.dev/docs/hooks/types/#mcp-tool-hooks, 2026-10-10).
_MCP_PREFIX = "mcp_"
_CLAUDE_MCP_PREFIX = "mcp__"


def looks_like_claude_code(raw):
    """True when the payload carries a field only Claude Code has been seen to send."""
    return isinstance(raw, dict) and any(marker in raw for marker in OBSERVED_MARKERS)


def names_a_single_underscore_mcp_tool(raw):
    """True when tool_name is an MCP tool ID in a spelling Claude Code never sends."""
    name = raw.get("tool_name") if isinstance(raw, dict) else None
    return isinstance(name, str) and name.startswith(_MCP_PREFIX) and not name.startswith(_CLAUDE_MCP_PREFIX)


def event_keys_agree(raw):
    """True when hookEventName names hook_event_name's event: the same text, or Grok Build's snake_case twin."""
    snake, pascal = (raw.get("hookEventName"), raw.get("hook_event_name")) if isinstance(raw, dict) else (None, None)
    if not isinstance(pascal, str) or not isinstance(snake, str):
        return False
    return snake == pascal or (snake.islower() and snake.replace("_", "") == pascal.lower())


PROBES = {
    "looks_like_claude_code": looks_like_claude_code,
    "names_a_single_underscore_mcp_tool": names_a_single_underscore_mcp_tool,
    "event_keys_agree": event_keys_agree,
}
