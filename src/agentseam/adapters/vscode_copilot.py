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
    SESSION_START,
    STOP,
    SUBAGENT_START,
    SUBAGENT_STOP,
    UNKNOWN,
    VOUCH,
    Event,
    tool_input_of,
)
from ._copilot_claims import (  # noqa: F401 (claims is this adapter's interface, defined
    # with the rest of the identification side in _copilot_claims and re-exported here)
    _CLI_ARGS,
    _CLI_RESULT,
    _CLI_STOP,
    EVENT_KEYS,
    EVENT_MAP,
    MEMORY_TOOLS,
    _name,
    claims,
    is_cli_native,
)
from ._windows import powershell_command

AGENT = "vscode_copilot"

MEMORY_WRITE_COMMANDS = ("create", "str_replace", "insert")

#: Copilot's hooks reference ("Tool names for hook matching", read 2026-09-01): runtime
#: names bash (Unix) / powershell (Windows), reported as Claude's Bash in PascalCase payloads.
SHELL_TOOLS = ("bash", "powershell", "Bash")


def _tool_input(raw):
    """The tool's arguments: VS Code's `tool_input`, else the CLI's `toolArgs` (object or JSON text)."""
    ti = raw.get("tool_input")
    return tool_input_of(raw.get(_CLI_ARGS) if ti is None else ti)


def _cli_output(raw):
    """Copilot's result object: camelCase, or its VS Code compatible snake_case twin."""
    result = raw.get(_CLI_RESULT) or raw.get("tool_result")
    if isinstance(result, dict):
        return result.get("textResultForLlm") or result.get("text_result_for_llm")
    return None


def _implied_name(raw):
    """The event a payload with no name of its own is: agentStop, postToolUse, else preToolUse."""
    if _CLI_STOP in raw and _CLI_ARGS not in raw:
        return "agentStop"
    return "postToolUse" if _CLI_RESULT in raw else "preToolUse"


def parse(raw):
    if not isinstance(raw, dict):
        return Event(AGENT, UNKNOWN, raw=raw)
    ti = _tool_input(raw)
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
        content = ti.get("content") or ti.get("newText") or ti.get("new_str") or ti.get("file_text")
    name = _name(raw) or _implied_name(raw)
    return Event(
        AGENT,
        EVENT_MAP.get(name, UNKNOWN),
        tool=tool,
        command=ti.get("command") if tool not in MEMORY_TOOLS else None,
        path=path,
        content=content,
        prompt=raw.get("prompt"),
        output=raw.get("tool_output") or raw.get("tool_response") or _cli_output(raw),
        session_id=raw.get("session_id") or raw.get("sessionId"),
        tool_use_id=raw.get("tool_use_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def is_memory_write(event):
    """True when this event is a memory-tool content write (VS Code's memory surface)."""
    ti = _tool_input(event.raw)
    return event.tool in MEMORY_TOOLS and ti.get("command") in MEMORY_WRITE_COMMANDS


_TOP_LEVEL_BLOCK = (PROMPT_SUBMIT, POST_TOOL)

_NESTED_BLOCK = (STOP, SUBAGENT_STOP)


def _echoed_name(event):
    """This event's own vendor spelling, out of the payload; VS Code's name if there is none."""
    return _name(event.raw) or REVERSE_EVENT_MAP.get(event.event, "PreToolUse")


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


def _top_level_block_body(decision):
    """The dict to serialize, or None where nothing blocks -- always exit 0."""
    if decision.outcome in (ALLOW, VOUCH):
        return None
    return {"decision": "block", "reason": _refusal_reason(decision)}


def _nested_block_body(decision, event):
    if decision.outcome in (ALLOW, VOUCH):
        return None
    out = {"hookEventName": _echoed_name(event), "decision": "block", "reason": _refusal_reason(decision)}
    return {"hookSpecificOutput": out}


def _pre_tool_out(decision, event):
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
    elif decision.outcome == REWRITE and decision.updated_input is not None:
        out["permissionDecision"] = "allow"
        out["updatedInput"] = decision.updated_input
        if decision.reason:
            out[_PERMISSION_DECISION_REASON] = decision.reason
    elif decision.outcome == REWRITE:
        out["permissionDecision"] = "deny"
        out[_PERMISSION_DECISION_REASON] = (decision.reason or "blocked") + " (no replacement input was supplied)"
    return out


def _cli_pre_tool_out(decision):
    """The CLI's documented top-level answer; it has no input rewrite, so a rewrite blocks."""
    if decision.outcome == VOUCH:
        out = {"permissionDecision": "allow"}
        if decision.reason:
            out[_PERMISSION_DECISION_REASON] = decision.reason
        return out
    if decision.outcome == ASK:
        return {"permissionDecision": "ask", _PERMISSION_DECISION_REASON: decision.reason or "confirmation required"}
    return {"permissionDecision": "deny", _PERMISSION_DECISION_REASON: _refusal_reason(decision)}


def respond(decision, event):
    """Three dialects, one per event group -- not one gate shape everywhere."""
    import json as _json  # noqa: PLC0415 (bundler.py keeps this vendored file's own function-local
    # imports untouched -- only top-level imports get hoisted into a bundle; see
    # test_function_local_imports_are_left_alone -- so hoisting this would only move it, not
    # remove it, while touching every response line for no behavioral gain)

    if event.event in _TOP_LEVEL_BLOCK:
        body = _top_level_block_body(decision)
        return ("", 0) if body is None else (_json.dumps(body), 0)

    if event.event in _NESTED_BLOCK:
        body = _nested_block_body(decision, event)
        return ("", 0) if body is None else (_json.dumps(body), 0)

    if event.event != PRE_TOOL or decision.outcome == ALLOW:
        return "", 0

    if is_cli_native(event.raw):
        return _json.dumps(_cli_pre_tool_out(decision)), 0

    return _json.dumps({"hookSpecificOutput": _pre_tool_out(decision, event)}), 0


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
            windows = powershell_command(command)
            entry = {"type": "command", "command": command, "bash": command, "powershell": windows, "windows": windows}
            hooks.setdefault(name, []).append(entry)
    return {"hooks": hooks}


CONFIG_PATH = ".github/hooks/agentseam.json"
