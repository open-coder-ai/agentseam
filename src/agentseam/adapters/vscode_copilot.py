"""VS Code Copilot (agent mode) and GitHub Copilot CLI adapter."""

from __future__ import annotations

from ..contract import (
    ALLOW,
    ASK,
    DENY,
    POST_TOOL,
    PRE_TOOL,
    PROMPT_SUBMIT,
    REWRITE,
    SESSION_END,
    SESSION_START,
    STOP,
    SUBAGENT_START,
    SUBAGENT_STOP,
    UNKNOWN,
    VOUCH,
    Event,
    tool_input_of,
)
from ._windows import powershell_command

AGENT = "vscode_copilot"

EVENT_MAP = {
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "SessionStart": SESSION_START,
    "SubagentStart": SUBAGENT_START,
    "SubagentStop": SUBAGENT_STOP,
    "Stop": STOP,
    "preToolUse": PRE_TOOL,
    "postToolUse": POST_TOOL,
    "userPromptSubmitted": PROMPT_SUBMIT,
    "sessionStart": SESSION_START,
    "sessionEnd": SESSION_END,
    "subagentStop": SUBAGENT_STOP,
    "agentStop": STOP,
}

MEMORY_TOOLS = ("memory", "copilot_memory")
MEMORY_WRITE_COMMANDS = ("create", "str_replace", "insert")

#: Copilot's hooks reference ("Tool names for hook matching", read 2026-09-01): runtime
#: names bash (Unix) / powershell (Windows), reported as Claude's Bash in PascalCase payloads.
SHELL_TOOLS = ("bash", "powershell", "Bash")


_CODEX_MARKERS = ("turn_id", "permission_mode")

_CURSOR_MARKERS = ("model", "cursor_version", "conversation_id", "generation_id", "workspace_roots")

_CLAIMABLE = tuple(name for name in EVENT_MAP if name[:1].islower())

_VSCODE_ENVELOPE = "timestamp"


def claims(raw):
    """True for a payload from either product."""
    if not isinstance(raw, dict):
        return False
    name = raw.get("hook_event_name") or raw.get("hookEventName")
    if name in EVENT_MAP and _VSCODE_ENVELOPE in raw and "turn_id" not in raw:
        return True
    if any(k in raw for k in _CODEX_MARKERS + _CURSOR_MARKERS):
        return False
    if name in _CLAIMABLE:
        return True
    ti = raw.get("tool_input")
    return raw.get("tool_name") in MEMORY_TOOLS and isinstance(ti, dict) and "command" in ti


def parse(raw):
    ti = raw.get("tool_input")
    ti = tool_input_of(ti)
    tool = raw.get("tool_name") or raw.get("toolName")
    path = content = None
    if tool in MEMORY_TOOLS:
        if ti.get("command") in MEMORY_WRITE_COMMANDS:
            path = ti.get("path") or "/memories/"
            content = ti.get("file_text") or ti.get("new_str") or ti.get("insert_text")
        else:
            path = ti.get("path")
    else:
        path = ti.get("filePath") or ti.get("file_path") or ti.get("path")
        content = ti.get("content") or ti.get("newText") or ti.get("new_str")
    name = raw.get("hook_event_name") or raw.get("hookEventName") or "preToolUse"
    return Event(
        AGENT,
        EVENT_MAP.get(name, UNKNOWN),
        tool=tool,
        command=ti.get("command") if tool not in MEMORY_TOOLS else None,
        path=path,
        content=content,
        prompt=raw.get("prompt"),
        output=raw.get("tool_output") or raw.get("tool_response"),
        session_id=raw.get("session_id"),
        tool_use_id=raw.get("tool_use_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def is_memory_write(event):
    """True when this event is a memory-tool content write (VS Code's memory surface)."""
    ti = event.raw.get("tool_input")
    ti = tool_input_of(ti)
    return event.tool in MEMORY_TOOLS and ti.get("command") in MEMORY_WRITE_COMMANDS


_TOP_LEVEL_BLOCK = (PROMPT_SUBMIT, POST_TOOL)

_NESTED_BLOCK = (STOP, SUBAGENT_STOP)


def _echoed_name(event):
    """This event's own vendor spelling, out of the payload; VS Code's name if there is none."""
    raw = event.raw or {}
    return raw.get("hook_event_name") or raw.get("hookEventName") or REVERSE_EVENT_MAP.get(event.event, "PreToolUse")


def _refusal_reason(decision):
    """One reason string for the block dialects, which have no ask and no rewrite."""
    reason = decision.reason or "blocked by policy"
    if decision.outcome == ASK:
        return reason + " (confirmation requested; this event cannot prompt, so it blocks)"
    if decision.outcome == REWRITE:
        return reason + " (input rewrite requested; this event cannot modify input, so it blocks)"
    return reason


DECISION_VOCABULARY = frozenset({"allow", "deny", "ask", "block"})

#: The permission-object dialect's one reason field, named four times below.
_PERMISSION_DECISION_REASON = "permissionDecisionReason"


def respond(decision, event):
    """Three dialects, one per event group -- not one gate shape everywhere."""
    import json as _json  # noqa: PLC0415 (bundler.py keeps this vendored file's own function-local
    # imports untouched -- only top-level imports get hoisted into a bundle; see
    # test_function_local_imports_are_left_alone -- so hoisting this would only move it, not
    # remove it, while touching every response line for no behavioral gain)

    if event.event in _TOP_LEVEL_BLOCK:
        if decision.outcome in (ALLOW, VOUCH):
            return "", 0
        return _json.dumps({"decision": "block", "reason": _refusal_reason(decision)}), 0

    if event.event in _NESTED_BLOCK:
        if decision.outcome in (ALLOW, VOUCH):
            return "", 0
        out = {"hookEventName": _echoed_name(event), "decision": "block", "reason": _refusal_reason(decision)}
        return _json.dumps({"hookSpecificOutput": out}), 0

    if event.event != PRE_TOOL:
        return "", 0

    if decision.outcome == ALLOW:
        return "", 0

    out = {"hookEventName": _echoed_name(event)}
    if decision.outcome == VOUCH:
        out["permissionDecision"] = "allow"
        if decision.reason:
            out[_PERMISSION_DECISION_REASON] = decision.reason
    elif decision.outcome == DENY:
        out["permissionDecision"] = "deny"
        out[_PERMISSION_DECISION_REASON] = decision.reason or "blocked"
    elif decision.outcome == ASK:
        out["permissionDecision"] = "ask"
        out[_PERMISSION_DECISION_REASON] = decision.reason or "confirmation required"
    elif decision.outcome == REWRITE:
        out["permissionDecision"] = "allow"
        out["updatedInput"] = decision.updated_input
        if decision.reason:
            out[_PERMISSION_DECISION_REASON] = decision.reason
    return _json.dumps({"hookSpecificOutput": out}), 0


REVERSE_EVENT_MAP = {
    PRE_TOOL: "PreToolUse",
    POST_TOOL: "PostToolUse",
    PROMPT_SUBMIT: "UserPromptSubmit",
    SESSION_START: "SessionStart",
    SUBAGENT_START: "SubagentStart",
    SUBAGENT_STOP: "SubagentStop",
    STOP: "Stop",
}


def hook_config(canonical_events, command, matcher=None):  # noqa: ARG001 (every adapter's
    # hook_config(..., matcher=) is called uniformly by install.py/install_identity.py;
    # VS Code has no per-tool matcher to honour, but the parameter stays for interface parity)
    """The hooks file VS Code actually parses: an object keyed by event name."""
    hooks = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if name:
            entry = {"type": "command", "command": command, "windows": powershell_command(command)}
            hooks.setdefault(name, []).append(entry)
    return {"hooks": hooks}


CONFIG_PATH = ".github/hooks/agentseam.json"
