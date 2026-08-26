"""VS Code Copilot (agent mode) adapter.

Same PreToolUse wire contract as Claude Code — verified in microsoft/vscode source:
IPreToolUseHookCommandInput {tool_name, tool_input} in, hookSpecificOutput
{permissionDecision: allow|deny|ask, permissionDecisionReason, updatedInput} out; the
deny is honored in languageModelToolsService.invokeTool.

The difference that matters: a memory write here is the `memory` tool
(create/str_replace/insert on /memories/...), not a file edit.
"""

from __future__ import annotations

from ..contract import (
    ASK,
    DENY,
    POST_TOOL,
    PRE_TOOL,
    PROMPT_SUBMIT,
    REWRITE,
    SESSION_END,
    SESSION_START,
    TOOL_FAILURE,
    Event,
)

AGENT = "vscode_copilot"

EVENT_MAP = {
    "preToolUse": PRE_TOOL,
    "PreToolUse": PRE_TOOL,
    "postToolUse": POST_TOOL,
    "PostToolUse": POST_TOOL,
    "postToolUseFailure": TOOL_FAILURE,
    "userPromptSubmitted": PROMPT_SUBMIT,
    "sessionStart": SESSION_START,
    "sessionEnd": SESSION_END,
}

MEMORY_TOOLS = ("memory", "copilot_memory")
MEMORY_WRITE_COMMANDS = ("create", "str_replace", "insert")
FILE_WRITE_TOOLS = ("create_file", "edit_file", "apply_patch")


def claims(raw):
    if not isinstance(raw, dict):
        return False
    name = raw.get("hook_event_name") or raw.get("hookEventName")
    if name in ("preToolUse", "postToolUse", "userPromptSubmitted", "sessionStart", "sessionEnd"):
        return True
    # memory-tool payloads are unmistakable
    ti = raw.get("tool_input") or {}
    return raw.get("tool_name") in MEMORY_TOOLS and isinstance(ti, dict) and "command" in ti


def parse(raw):
    ti = raw.get("tool_input") or {}
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
        EVENT_MAP.get(name, PRE_TOOL),
        tool=tool,
        command=ti.get("command") if tool not in MEMORY_TOOLS else None,
        path=path,
        content=content,
        output=raw.get("tool_output"),
        session_id=raw.get("session_id"),
        tool_use_id=raw.get("tool_use_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def is_memory_write(event):
    """True when this event is a memory-tool content write (VS Code's memory surface)."""
    ti = event.raw.get("tool_input") or {}
    return event.tool in MEMORY_TOOLS and ti.get("command") in MEMORY_WRITE_COMMANDS


def respond(decision, event):
    import json as _json

    out = {"hookEventName": "PreToolUse"}
    if decision.outcome == DENY:
        out["permissionDecision"] = "deny"
        out["permissionDecisionReason"] = decision.reason or "blocked"
    elif decision.outcome == ASK:
        out["permissionDecision"] = "ask"
        out["permissionDecisionReason"] = decision.reason or "confirmation required"
    elif decision.outcome == REWRITE:
        out["permissionDecision"] = "allow"
        out["updatedInput"] = decision.updated_input
    else:
        out["permissionDecision"] = "allow"
    return _json.dumps({"hookSpecificOutput": out}), 0


def hook_config(canonical_events, command, matcher=None):
    reverse = {
        PRE_TOOL: "preToolUse",
        POST_TOOL: "postToolUse",
        PROMPT_SUBMIT: "userPromptSubmitted",
        SESSION_START: "sessionStart",
        SESSION_END: "sessionEnd",
    }
    hooks = []
    for ev in canonical_events:
        name = reverse.get(ev)
        if name:
            entry = {"event": name, "command": command}
            if matcher:
                entry["matcher"] = matcher
            hooks.append(entry)
    return {"version": 1, "hooks": hooks}


CONFIG_PATH = ".github/hooks/agentseam.json"
