"""Claude Code adapter."""

from __future__ import annotations

from ..contract import (
    ALLOW,
    ASK,
    DENY,
    FILE_CHANGED,
    INSTRUCTIONS_LOADED,
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
    UNKNOWN,
    VOUCH,
    Event,
    tool_input_of,
)

AGENT = "claude_code"

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
    "InstructionsLoaded": INSTRUCTIONS_LOADED,
    "FileChanged": FILE_CHANGED,
}
REVERSE_EVENT_MAP = {v: k for k, v in EVENT_MAP.items()}

WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")

SHELL_TOOLS = ("Bash",)


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


def claims(raw):
    """True when this payload looks like Claude Code's shape."""
    if not isinstance(raw, dict):
        return False
    if raw.get("hook_event_name") in EVENT_MAP:
        if raw.get("client_type") not in (None, "claude_code"):
            return False
        if "turn_id" in raw or "project_path" in raw or "timestamp" in raw:
            return False
        if "prompt_id" in raw and not looks_like_claude_code(raw):
            return False
        return True
    return False


def parse(raw):
    ti = raw.get("tool_input")
    ti = tool_input_of(ti)
    tool = raw.get("tool_name")
    content = ti.get("content") or ti.get("new_string") or ti.get("new_source") or None
    if content is None and isinstance(ti.get("edits"), list):
        joined = "\n".join(str(e.get("new_string", "")) for e in ti["edits"] if isinstance(e, dict))
        content = joined or None
    out = raw.get("tool_output")
    if isinstance(out, (dict, list)):
        import json as _json

        out = _json.dumps(out)
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
        tool=tool,
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("path") or ti.get("notebook_path") or raw.get("file_path"),
        content=content or raw.get("content"),
        output=out,
        prompt=raw.get("prompt"),
        session_id=raw.get("session_id"),
        tool_use_id=raw.get("tool_use_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


_BLOCK_DIALECT_EVENTS = (PROMPT_SUBMIT, STOP)


def _refusal_reason(decision):
    """One reason string for the events that can only block -- no ask, no rewrite."""
    reason = decision.reason or "blocked by policy"
    if decision.outcome == ASK:
        return reason + " (confirmation requested; this event cannot prompt, so it blocks)"
    if decision.outcome == REWRITE:
        return reason + " (input rewrite requested; this event cannot modify input, so it blocks)"
    return reason


DECISION_VOCABULARY = frozenset({"allow", "deny", "ask", "block"})


def _additional_context_output(event, context):
    return {
        "hookSpecificOutput": {
            "hookEventName": REVERSE_EVENT_MAP.get(event.event, "PreToolUse"),
            "additionalContext": context,
        }
    }


def respond(decision, event):
    """(stdout_text, exit_code) for this decision -- three dialects, not one."""
    import json as _json

    if event.event in _BLOCK_DIALECT_EVENTS:
        out = {} if decision.outcome in (ALLOW, VOUCH) else {"decision": "block", "reason": _refusal_reason(decision)}
        if event.event == PROMPT_SUBMIT and decision.context:
            out.update(_additional_context_output(event, decision.context))
        return (_json.dumps(out), 0) if out else ("", 0)

    if event.event == SESSION_START:
        if decision.context:
            return _json.dumps(_additional_context_output(event, decision.context)), 0
        return "", 0

    if event.event != PRE_TOOL:
        return "", 0

    if decision.outcome == ALLOW:
        return "", 0

    out = {"hookEventName": REVERSE_EVENT_MAP.get(event.event, "PreToolUse")}
    if decision.outcome == VOUCH:
        out["permissionDecision"] = "allow"
        if decision.reason:
            out["permissionDecisionReason"] = decision.reason
    elif decision.outcome == DENY:
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
