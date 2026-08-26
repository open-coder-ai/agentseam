"""Claude Code adapter.

Payload: {"tool_name", "tool_input", "session_id", "tool_use_id", "hook_event_name", ...}
Response: {"hookSpecificOutput": {"hookEventName", "permissionDecision", ...}} on stdout;
exit 2 also blocks. Verified live against Claude Code 2.1.245 (2026-08-25).
"""

from __future__ import annotations

from ..contract import (
    ASK,
    DENY,
    POST_TOOL,
    PRE_COMPACT,
    PRE_TOOL,
    PROMPT_SUBMIT,
    REWRITE,
    SESSION_END,
    SESSION_START,
    STOP,
    SUBAGENT_START,
    SUBAGENT_STOP,
    TOOL_FAILURE,
    Event,
)

AGENT = "claude_code"

# vendor event name -> canonical
EVENT_MAP = {
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "PostToolUseFailure": TOOL_FAILURE,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "Stop": STOP,
    "PreCompact": PRE_COMPACT,
    "SubagentStart": SUBAGENT_START,
    "SubagentStop": SUBAGENT_STOP,
}
REVERSE_EVENT_MAP = {v: k for k, v in EVENT_MAP.items()}

# Tools whose input carries file content rather than a shell command.
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def claims(raw):
    """True when this payload looks like Claude Code's shape."""
    if not isinstance(raw, dict):
        return False
    if raw.get("hook_event_name") in EVENT_MAP:
        # Codex reuses tool_input but adds turn identifiers; don't claim those.
        return "turn_id" not in raw
    return False


def parse(raw):
    ti = raw.get("tool_input") or {}
    tool = raw.get("tool_name")
    content = ti.get("content") or ti.get("new_string") or None
    if content is None and isinstance(ti.get("edits"), list):
        joined = "\n".join(str(e.get("new_string", "")) for e in ti["edits"])
        content = joined or None
    out = raw.get("tool_output")
    if isinstance(out, (dict, list)):
        import json as _json

        out = _json.dumps(out)
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hook_event_name"), raw.get("hook_event_name")),
        tool=tool,
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("path") or ti.get("notebook_path"),
        content=content,
        output=out,
        prompt=raw.get("prompt"),
        session_id=raw.get("session_id"),
        tool_use_id=raw.get("tool_use_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def respond(decision, event):
    """(stdout_text, exit_code) for this decision."""
    hook_name = REVERSE_EVENT_MAP.get(event.event, "PreToolUse")
    out = {"hookEventName": hook_name}
    if decision.outcome == DENY:
        out["permissionDecision"] = "deny"
        out["permissionDecisionReason"] = decision.reason or "blocked"
    elif decision.outcome == ASK:
        out["permissionDecision"] = "ask"
        out["permissionDecisionReason"] = decision.reason or "confirmation required"
    elif decision.outcome == REWRITE:
        out["permissionDecision"] = "allow"
        out["updatedInput"] = decision.updated_input
        if decision.reason:
            out["permissionDecisionReason"] = decision.reason
    else:
        out["permissionDecision"] = "allow"
    import json as _json

    return _json.dumps({"hookSpecificOutput": out}), 0


def hook_config(canonical_events, command, matcher=None):
    """A settings.json `hooks` fragment wiring `command` for these canonical events."""
    hooks = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        entry = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            entry["matcher"] = matcher
        hooks.setdefault(name, []).append(entry)
    return {"hooks": hooks}


CONFIG_PATH = ".claude/settings.json"
