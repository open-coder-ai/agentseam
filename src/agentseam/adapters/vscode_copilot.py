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
    UNKNOWN,
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
# A FILE_WRITE_TOOLS constant naming create_file/edit_file/apply_patch used to sit here,
# declared and read by nothing -- misleading, since it implied write-tool-specific content
# extraction that does not exist. The generic parse branch below reads content/newText/
# new_str regardless of tool name, and none of those three tools' actual tool_input shape
# for edit_file (code? a diff?) or apply_patch (the patch text, under what key?) has been
# recorded from a real payload or the vendor source cited above. Needs a live capture
# before adding a fallback -- guessing a key here risks reading the wrong field silently.


#: Turn-scoped fields OpenAI Codex CLI sends and VS Code never does.
_CODEX_MARKERS = ("turn_id", "permission_mode")

#: Cursor's base hook schema, present on every one of its events.
_CURSOR_MARKERS = ("model", "cursor_version", "conversation_id", "generation_id", "workspace_roots")


#: The event names that identify VS Code Copilot, derived from EVENT_MAP rather than kept
#: by hand -- the hand-kept list had drifted, leaving postToolUseFailure parseable and
#: claimed by the matrix but claimed by no adapter, so those payloads went unidentified and
#: an unidentified payload is allowed through.
#:
#: camelCase only. EVENT_MAP also holds PascalCase aliases so a payload spelled Claude
#: Code's way still parses, but claiming on those would take Claude Code's own payloads --
#: parse tolerance and identification are different jobs.
_CLAIMABLE = tuple(name for name in EVENT_MAP if name[:1].islower())


def claims(raw):
    if not isinstance(raw, dict):
        return False
    # Codex CLI and Cursor both spell their events in the same camelCase, and neither
    # difference is in the event name -- so the only thing separating the three payloads is
    # the fields the other two carry. Without this guard two adapters claim the event,
    # detection goes ambiguous, and the dispatcher allows a write it was asked to gate.
    #
    # Each vendor gets more than one marker on purpose. Resting on a single field means
    # resting on another vendor never dropping it: Cursor's `model` alone kept these two
    # apart until a payload without it turned up, and both adapters claimed it.
    if any(k in raw for k in _CODEX_MARKERS + _CURSOR_MARKERS):
        return False
    if (raw.get("hook_event_name") or raw.get("hookEventName")) in _CLAIMABLE:
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
        # An event this adapter has no mapping for resolves to UNKNOWN, never to the
        # nearest canonical one: relabelling it invites a guardrail to evaluate the
        # wrong policy against it.
        EVENT_MAP.get(name, UNKNOWN),
        tool=tool,
        command=ti.get("command") if tool not in MEMORY_TOOLS else None,
        path=path,
        content=content,
        # userPromptSubmitted parses to prompt_submit, but the prompt text was never read,
        # so a prompt-based policy saw None and was silently dead on this agent. Its peers
        # sharing this envelope (claude_code, gemini_cli) both read `prompt`.
        prompt=raw.get("prompt"),
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


#: Canonical -> vendor event, for installing. Module level so `install` can see which
#: events an adapter is able to wire; an inline map made that invisible, and an event the
#: matrix claimed but this could not name was dropped from the config without a word.
REVERSE_EVENT_MAP = {
    PRE_TOOL: "preToolUse",
    POST_TOOL: "postToolUse",
    TOOL_FAILURE: "postToolUseFailure",
    PROMPT_SUBMIT: "userPromptSubmitted",
    SESSION_START: "sessionStart",
    SESSION_END: "sessionEnd",
}


def hook_config(canonical_events, command, matcher=None):
    hooks = []
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if name:
            entry = {"event": name, "command": command}
            if matcher:
                entry["matcher"] = matcher
            hooks.append(entry)
    return {"version": 1, "hooks": hooks}


CONFIG_PATH = ".github/hooks/agentseam.json"
