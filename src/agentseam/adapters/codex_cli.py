"""OpenAI Codex CLI adapter."""

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
    UNKNOWN,
    Event,
    tool_input_of,
)
from ._windows import powershell_command  # noqa: E402,F401

AGENT = "codex_cli"

EVENT_MAP = {
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "PreCompact": PRE_COMPACT,
    "Stop": STOP,
    "SubagentStart": SUBAGENT_START,
    "SubagentStop": SUBAGENT_STOP,
}
REVERSE_EVENT_MAP = {v: k for k, v in EVENT_MAP.items()}


_SESSION_START_FIELDS = ("session_id", "transcript_path", "cwd", "model", "permission_mode", "source")


def claims(raw):
    """Codex's PreToolUse carries turn_id; Claude Code's does not."""
    if not isinstance(raw, dict):
        return False
    name = raw.get("hook_event_name")
    if name not in EVENT_MAP:
        return False
    if "turn_id" in raw:
        return True
    return name == "SessionStart" and all(field in raw for field in _SESSION_START_FIELDS)


def parse(raw):
    """Normalise one payload."""
    ti = tool_input_of(raw.get("tool_input"))
    content = ti.get("content")
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
        tool=raw.get("tool_name"),
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("path"),
        content=content,
        output=raw.get("tool_output"),
        prompt=raw.get("prompt"),
        session_id=raw.get("session_id"),
        tool_use_id=raw.get("tool_use_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def _because(reason, note):
    return "%s (%s)" % (reason, note) if reason else note


_BLOCK_DIALECT_EVENTS = (PROMPT_SUBMIT, STOP)


DECISION_VOCABULARY = frozenset({"allow", "deny", "block"})


def respond(decision, event):
    """Always exit 0 and carry the verdict in JSON, in the dialect THIS event accepts."""
    import json as _json

    if event.event == PRE_TOOL:
        return _pre_tool_response(decision)
    if event.event in _BLOCK_DIALECT_EVENTS:
        if decision.outcome in (DENY, ASK, REWRITE):
            return _json.dumps({"decision": "block", "reason": _refusal_reason(decision)}), 0
        return "", 0
    return "", 0


def _refusal_reason(decision):
    """The reason text for a refusal, annotated when the decision had to be degraded."""
    if decision.outcome == ASK:
        return _because(decision.reason, "Codex CLI cannot prompt for confirmation at this event")
    if decision.outcome == REWRITE:
        return _because(decision.reason, "Codex CLI cannot modify a tool call at this event")
    return decision.reason or "blocked by policy"


def _pre_tool_response(decision):
    """The permissionDecision gate, the one place Codex reads a permission verdict."""
    import json as _json

    out = {"hookEventName": "PreToolUse"}
    if decision.outcome == REWRITE and decision.updated_input is not None:
        out["permissionDecision"] = "allow"
        out["updatedInput"] = decision.updated_input
        if decision.reason:
            out["permissionDecisionReason"] = decision.reason
    elif decision.outcome in (DENY, ASK, REWRITE):
        out["permissionDecision"] = "deny"
        note = None
        if decision.outcome == ASK:
            note = "Codex CLI does not support ask; asking would fail open"
        elif decision.outcome == REWRITE:
            note = "Codex CLI cannot apply a rewrite with no updatedInput"
        out["permissionDecisionReason"] = _because(decision.reason, note) if note else (decision.reason or "blocked")
    else:
        return "", 0
    return _json.dumps({"hookSpecificOutput": out}), 0


def hook_config(canonical_events, command, matcher=None):
    """ConfiguredHookMatcherGroup shape: {matcher, hooks: [{type: command, ...}]}."""
    hooks = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        entry = {"hooks": [{"type": "command", "command": command, "commandWindows": powershell_command(command)}]}
        if matcher:
            entry["matcher"] = matcher
        hooks.setdefault(name, []).append(entry)
    return {"hooks": hooks}


CONFIG_PATH = ".codex/hooks.json"
