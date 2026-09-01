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


def looks_like_claude_code(raw):
    """True when the payload carries a field only Claude Code has been seen to send."""
    return isinstance(raw, dict) and any(marker in raw for marker in OBSERVED_MARKERS)


PROBES = {"looks_like_claude_code": looks_like_claude_code}
