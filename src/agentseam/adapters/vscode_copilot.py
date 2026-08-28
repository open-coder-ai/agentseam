"""VS Code Copilot (agent mode) and GitHub Copilot CLI adapter.

Two vendors, one hook surface, two spellings of every event name -- `HOOKS_BY_TARGET` in
microsoft/vscode's `hookTypes.ts` gives both maps side by side, PascalCase for
Target.VSCode and camelCase for Target.GitHubCopilot. See EVENT_MAP below.

Neither list contains `postToolUseFailure`, which this adapter mapped, claimed on and
installed for until 2026-08-28: the config key resolves to nothing and is dropped, so an
install for tool_failure wired a hook that could never fire.

PreToolUse wire contract (hookCommandTypes.ts): IPreToolUseHookCommandInput {tool_name,
tool_input, tool_use_id} plus the envelope executeHook merges into every event
({timestamp, hook_event_name, session_id, transcript_path, cwd?}); out, hookSpecificOutput
{permissionDecision: allow|deny|ask, permissionDecisionReason, updatedInput,
additionalContext}, honoured in languageModelToolsService.invokeTool.

The difference that matters for policy: a memory write is the `memory` tool
(create/str_replace/insert on /memories/...), not a file edit.
"""

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
    Event,
)
from ._windows import powershell_command

AGENT = "vscode_copilot"

#: Every vendor event name, in both spellings; parsing accepts both. `errorOccurred` is
#: absent: it reports a session error, not a tool failure, so mapping it to TOOL_FAILURE
#: would have a guardrail judge a tool policy against a payload with no tool. PreCompact
#: is absent too: VS Code's schema and docs list it, but it is never fired.
EVENT_MAP = {
    # VS Code agent mode (Target.VSCode)
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "SessionStart": SESSION_START,
    "SubagentStart": SUBAGENT_START,
    "SubagentStop": SUBAGENT_STOP,
    "Stop": STOP,
    # GitHub Copilot CLI / coding agent (Target.GitHubCopilot)
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
# A FILE_WRITE_TOOLS constant naming create_file/edit_file/apply_patch used to sit here,
# read by nothing. The generic parse branch reads content/newText/new_str regardless of
# tool name, and no payload or vendor source read here records what edit_file or
# apply_patch actually sends. Needs a live capture: a guessed key reads the wrong field.


#: Turn-scoped fields OpenAI Codex CLI sends and VS Code never does.
_CODEX_MARKERS = ("turn_id", "permission_mode")

#: Cursor's base hook schema, present on every one of its events.
_CURSOR_MARKERS = ("model", "cursor_version", "conversation_id", "generation_id", "workspace_roots")

#: Copilot CLI's camelCase names, which no other vendor uses -- the name alone identifies
#: these. Derived from EVENT_MAP: a hand-kept list drifted, leaving payloads claimed by
#: the matrix but by no adapter, and so allowed through.
_CLAIMABLE = tuple(name for name in EVENT_MAP if name[:1].islower())

#: executeHook merges {timestamp, hook_event_name, session_id?, transcript_path?} into
#: EVERY VS Code payload. `timestamp` is the one field there that Claude Code -- whose
#: PascalCase names VS Code reuses exactly -- has never been observed to send, and
#: claude_code.claims() already declines on it. Tabnine sends it too, so SessionStart
#: stays ambiguous by design.
_VSCODE_ENVELOPE = "timestamp"


def claims(raw):
    """True for a payload from either product.

    Until 2026-08-28 this claimed camelCase only, so it never claimed a real VS Code
    payload: VS Code spells its events PascalCase, identically to Claude Code, so those
    went to claude_code alone and were answered in the wrong dialect at every event but one.
    """
    if not isinstance(raw, dict):
        return False
    name = raw.get("hook_event_name") or raw.get("hookEventName")
    # Positive evidence first: Cursor's `model` is in the exclusion list below and VS
    # Code's SessionStartHookInput carries `model` too, so running the exclusions first
    # rejected exactly the payload the envelope test identifies.
    if name in EVENT_MAP and _VSCODE_ENVELOPE in raw and "turn_id" not in raw:
        return True
    # Codex CLI and Cursor spell their events in this same camelCase and differ only in
    # the fields they carry, so without this guard two adapters claim the event, detection
    # goes ambiguous, and the dispatcher allows a write it was asked to gate. Each vendor
    # gets more than one marker on purpose: Cursor's `model` alone kept these apart until a
    # payload without it turned up, and then both adapters claimed it.
    if any(k in raw for k in _CODEX_MARKERS + _CURSOR_MARKERS):
        return False
    if name in _CLAIMABLE:
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
        # An unmapped event resolves to UNKNOWN, never to the nearest canonical one:
        # relabelling invites a guardrail to evaluate the wrong policy against it.
        EVENT_MAP.get(name, UNKNOWN),
        tool=tool,
        command=ti.get("command") if tool not in MEMORY_TOOLS else None,
        path=path,
        content=content,
        # The prompt text was once never read here, so a prompt policy saw None and was
        # silently dead; the envelope's peers (claude_code, gemini_cli) both read `prompt`.
        prompt=raw.get("prompt"),
        # IPostToolUseHookCommandInput names it `tool_response`. `tool_output` is Claude
        # Code's key, read here on an assumption, so event.output was always None on a real
        # PostToolUse payload and an output-inspecting policy was dead on this agent.
        output=raw.get("tool_output") or raw.get("tool_response"),
        session_id=raw.get("session_id"),
        tool_use_id=raw.get("tool_use_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def is_memory_write(event):
    """True when this event is a memory-tool content write (VS Code's memory surface)."""
    ti = event.raw.get("tool_input") or {}
    return event.tool in MEMORY_TOOLS and ti.get("command") in MEMORY_WRITE_COMMANDS


#: Events whose block verdict is a TOP-LEVEL {decision: "block", reason}.
#: UserPromptSubmitHookOutput declares exactly those two fields and
#: defaultIntentRequestHandler reads `typedOutput.decision` off the root object;
#: executePostToolUseHook reads the same two off a PostToolUse response's root, where a
#: block feeds the reason back to the model instead of the tool result.
_TOP_LEVEL_BLOCK = (PROMPT_SUBMIT, POST_TOOL)

#: Events whose block verdict is the same two fields NESTED in hookSpecificOutput.
#: executeStopHook requires BOTH -- `specific?.decision === 'block' && specific.reason` --
#: so a block with no reason is discarded and the agent stops anyway.
_NESTED_BLOCK = (STOP, SUBAGENT_STOP)


def _echoed_name(event):
    """This event's own vendor spelling, out of the payload; VS Code's name if there is none."""
    raw = event.raw or {}
    return raw.get("hook_event_name") or raw.get("hookEventName") or REVERSE_EVENT_MAP.get(event.event, "PreToolUse")


def _refusal_reason(decision):
    """One reason string for the block dialects, which have no ask and no rewrite.

    Both degrade to a block with the degradation named, rather than being dropped: silence
    here is the dispatcher's allow, which is not what the caller asked for.
    """
    reason = decision.reason or "blocked by policy"
    if decision.outcome == ASK:
        return reason + " (confirmation requested; this event cannot prompt, so it blocks)"
    if decision.outcome == REWRITE:
        return reason + " (input rewrite requested; this event cannot modify input, so it blocks)"
    return reason


#: Decision words accepted: permissionDecision's allow/deny/ask (hookCommandTypes.ts) plus the "block" the two decision dialects read.
DECISION_VOCABULARY = frozenset({"allow", "deny", "ask", "block"})


def respond(decision, event):
    """Three dialects, one per event group -- not one gate shape everywhere.

    Until 2026-08-28 this emitted the PreToolUse permission-decision JSON at every event.
    Elsewhere that shape is not merely ignored: UserPromptSubmit and PostToolUse read a
    top-level `decision`, Stop a nested one, and SessionStart/SubagentStart swallow
    everything under `ignoreErrors: true`. A deny there was theater.

    hookEventName is echoed rather than hardcoded: _toHookResult STRIPS hookSpecificOutput
    when the name does not match the event being run.
    """
    import json as _json

    if event.event in _TOP_LEVEL_BLOCK:
        if decision.outcome == ALLOW:
            return "", 0
        return _json.dumps({"decision": "block", "reason": _refusal_reason(decision)}), 0

    if event.event in _NESTED_BLOCK:
        if decision.outcome == ALLOW:
            return "", 0
        out = {"hookEventName": _echoed_name(event), "decision": "block", "reason": _refusal_reason(decision)}
        return _json.dumps({"hookSpecificOutput": out}), 0

    if event.event != PRE_TOOL:
        # What is left is SessionStart and SubagentStart, which take additionalContext and
        # nothing else and run under `ignoreErrors: true`, plus anything that reached
        # UNKNOWN. None of them has a verdict shape to speak in, so none gets one.
        return "", 0

    out = {"hookEventName": _echoed_name(event)}
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
    return _json.dumps({"hookSpecificOutput": out}), 0


#: Canonical -> vendor event, for installing. Module level so `install` can see which
#: events an adapter is able to wire; an inline map made that invisible, and an event the
#: matrix claimed but this could not name was dropped from the config without a word.
#:
#: PascalCase, i.e. VS Code's spelling, because CONFIG_PATH is VS Code's file.
#: `parseCopilotHooks` resolves each key with `resolveCopilotCliHookType(id) ?? toHookType
#: (id)`, so both spellings work there -- but only one may be written: it does
#: `result.set(hookType, ...)`, an overwrite, so two keys resolving to the same HookType
#: silently drop one. SESSION_END is therefore unwireable: `sessionEnd` is a Copilot CLI
#: name VS Code never fires, claimed for parsing and not offered for installing.
REVERSE_EVENT_MAP = {
    PRE_TOOL: "PreToolUse",
    POST_TOOL: "PostToolUse",
    PROMPT_SUBMIT: "UserPromptSubmit",
    SESSION_START: "SessionStart",
    SUBAGENT_START: "SubagentStart",
    SUBAGENT_STOP: "SubagentStop",
    STOP: "Stop",
}


def hook_config(canonical_events, command, matcher=None):
    """The hooks file VS Code actually parses: an object keyed by event name.

    Until 2026-08-28 this emitted `{"version": 1, "hooks": [{"event": ...}]}` -- a LIST
    under `hooks`, an `event` key, no `type`. All three are wrong and the failure is
    silent: `parseCopilotHooks` iterates `Object.keys(hooksObj)`, which over a list yields
    "0", "1", "2", resolving to no hook type. Zero hooks are installed, with no error. A
    top-level `version` also flips the schema to the Copilot CLI branch, which rejects
    `command`.

    `windows` is the vendor's own per-platform override (normalizeHookCommand in
    hookSchema.ts). It is needed because hookExecutor.ts spawns `powershell.exe -Command
    <hookCommand>` whenever ComSpec is cmd.exe -- the Windows default -- and PowerShell
    will not run a line beginning with a quoted path. Without it an install here fails
    exactly as Codex's did. `command` keeps the POSIX form, so the interpreter path that
    installed the hook survives.

    `matcher` is accepted and ignored: extractHookCommandsFromItem reads Claude's
    `{matcher, hooks: [...]}` shape but throws the matcher away, so there is no tool
    filtering here and emitting one would claim a narrower guard than exists.
    """
    hooks = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if name:
            entry = {"type": "command", "command": command, "windows": powershell_command(command)}
            hooks.setdefault(name, []).append(entry)
    return {"hooks": hooks}


CONFIG_PATH = ".github/hooks/agentseam.json"
