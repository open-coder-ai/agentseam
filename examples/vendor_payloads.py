"""One payload per (agent, event), in each vendor's own dialect.

Written from the vendor documentation behind each adapter, not copied from the test
fixtures: an example that only proves the tests agree with themselves proves nothing. The
tests that consume these check the property that matters -- each payload is claimed by
exactly the agent it is filed under, and parses to the event it is filed under.

The *story* is held constant per event so the pages compare. Every agent's `pre_tool` is the
same attempt to write a credential into a file it will read back later; every `tool_failure`
is the same failed test command. What differs between the pages is only the vendor's shape.
"""

from __future__ import annotations

from agentseam.contract import (
    FILE_CHANGED,
    INSTRUCTIONS_LOADED,
    POST_TOOL,
    PRE_COMPACT,
    PRE_TOOL,
    PROMPT_SUBMIT,
    SESSION_END,
    SESSION_START,
    STOP,
    SUBAGENT_START,
    SUBAGENT_STOP,
    TOOL_FAILURE,
)

#: Self-evident placeholder. A repository full of strings that pattern-match as credentials
#: teaches secret scanners to cry wolf, and this project's CI runs two of them.
SECRET = "AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY"
MEMORY_FILE = "AGENTS.md"
PROMPT = "remember my aws key so you can deploy later"
FAILING = "npm test"
FAILURE = "1 test failed"

#: The write tools each vendor names, so `pre_tool` really is a file write everywhere it
#: can be one. Windsurf has no file-write event at all, which its own entry handles.
_WRITE_TOOL = {
    "claude_code": "Write",
    "junie": "Write",
    "tabnine": "Write",
    "codex_cli": "Write",
    "cursor": "Write",
    "devin": "write_file",
    "gemini_cli": "write_file",
    "grok": "Write",
    "kimi_code": "Write",
}


def _tool_input(event):
    """The `tool_input` body for the tool-shaped events, shared by the snake_case vendors."""
    if event == PRE_TOOL:
        return {"file_path": MEMORY_FILE, "content": SECRET}
    return {"command": FAILING}


def _claude_shaped(agent, event, vendor_event, base, camel=False):
    """Vendors whose envelope is Claude Code's: {event, tool_name, tool_input, ...}.

    Grok spells the same fields in camelCase, which is the only thing separating its
    payloads from Claude Code's -- hence the flag rather than a second builder.
    """
    keys = (
        ("hookEventName", "toolName", "toolInput", "toolOutput")
        if camel
        else (
            "hook_event_name",
            "tool_name",
            "tool_input",
            "tool_output",
        )
    )
    ev, tool_k, in_k, out_k = keys
    raw = dict(base)
    raw[ev] = vendor_event

    if event in (PRE_TOOL, POST_TOOL, TOOL_FAILURE):
        raw[tool_k] = _WRITE_TOOL.get(agent, "Bash") if event == PRE_TOOL else "Bash"
        raw[in_k] = _tool_input(event)
        if event == POST_TOOL:
            raw[out_k] = "ok"
        if event == TOOL_FAILURE:
            raw[out_k] = FAILURE
            raw["error"] = FAILURE
    elif event == PROMPT_SUBMIT:
        raw["prompt"] = PROMPT
    elif event == SESSION_START:
        raw["source"] = "startup"
    elif event == SESSION_END:
        raw["reason"] = "exit"
    elif event in (SUBAGENT_START, SUBAGENT_STOP):
        raw["subagent_type"] = "explore"
    elif event == PRE_COMPACT:
        raw["trigger"] = "auto"
    elif event == INSTRUCTIONS_LOADED:
        raw["file_path"] = "CLAUDE.md"
        raw["content"] = "Prefer pnpm. Tests live beside source."
    elif event == FILE_CHANGED:
        raw["file_path"] = MEMORY_FILE
    return raw


#: Base envelope per vendor, from each one's documented common fields.
BASES = {
    # transcript_path and permission_mode are on every Claude Code payload the live capture
    # of 3.17.8 recorded, and they are what tells this envelope apart from the four vendors
    # that copy it. A base without them is a docs-era shape that agreed with a broken
    # discriminator all the way to production -- see CHANGELOG, "handed to Devin".
    "claude_code": {
        "session_id": "example",
        "cwd": "/repo",
        "transcript_path": "/repo/.claude/transcript.jsonl",
        "permission_mode": "default",
    },
    # `timestamp` is Tabnine's base-schema field and the only documented thing separating
    # its payloads from Gemini CLI's identically-named events.
    "tabnine": {"session_id": "example", "cwd": "/repo", "timestamp": "2026-08-26T00:00:00.000Z"},
    # `project_path` is what separates Junie from Claude Code, whose event names it reuses
    # deliberately so a hook script can be shared.
    "junie": {"session_id": "example", "cwd": "/repo", "project_path": "/repo"},
    "codex_cli": {
        "session_id": "example",
        "turn_id": "turn-1",
        "permission_mode": "auto",
        "model": "gpt-5-codex",
        "cwd": "/repo",
    },
    "devin": {"session_id": "example", "prompt_id": "turn-1"},
    "gemini_cli": {"session_id": "example", "cwd": "/repo"},
    "grok": {"sessionId": "example", "workspaceRoot": "/repo", "cwd": "/repo"},
    "kimi_code": {
        "session_id": "example",
        "session_title": "Fix login",
        "client_type": "kimi_code_cli",
        "cwd": "/repo",
    },
    # Cursor's base schema rides on every event, and `model` in particular is what keeps
    # VS Code Copilot from claiming these payloads too.
    "cursor": {
        "conversation_id": "example",
        "generation_id": "gen-1",
        "model": "claude-opus-4-7-thinking-max",
        "cursor_version": "1.7.2",
        "workspace_roots": ["/repo"],
        "cwd": "/repo",
    },
    "antigravity": {
        "conversationId": "example",
        "workspacePaths": ["/repo"],
        "modelName": "gemini-3.6-flash-medium",
    },
    "vscode_copilot": {"session_id": "example"},
    "windsurf": {"trajectory_id": "example"},
}


def _antigravity(event, vendor_event, base):
    """No event name in the payload at all: the event is inferred from shape.

    PostToolUse is separated from PreToolUse only by `error`, documented as empty rather
    than absent on success -- so the fixture carries it explicitly.
    """
    raw = dict(base)
    if event == PRE_TOOL:
        raw["toolCall"] = {"name": "write_to_file", "args": {"TargetFile": MEMORY_FILE, "CodeContent": SECRET}}
        raw["stepIdx"] = 3
    elif event == POST_TOOL:
        raw["toolCall"] = {"name": "run_command", "args": {"CommandLine": FAILING}}
        raw["stepIdx"] = 5
        raw["error"] = ""
    else:  # STOP
        raw.update(executionNum=1, terminationReason="model_stop", error="", fullyIdle=True)
    return raw


def _vscode(event, vendor_event, base):
    """Memory-tool payloads for the tool events; every event carries the common envelope.

    `chatHookService.executeHook` merges {timestamp, hook_event_name, session_id,
    transcript_path} into every payload before the caller's own fields, so `timestamp` and
    the snake_case key are on all of them. This builder used to emit `hookEventName` and no
    timestamp -- neither of which VS Code sends.
    """
    raw = dict(base, timestamp="2026-08-28T00:00:00.000Z", hook_event_name=vendor_event)
    if event == PRE_TOOL:
        raw.update(
            tool_name="memory", tool_input={"command": "create", "path": "/memories/team.md", "file_text": SECRET}
        )
        raw["tool_use_id"] = "example"
    elif event == POST_TOOL:
        # IPostToolUseHookCommandInput: tool_response, not Claude Code's tool_output.
        raw.update(tool_name="runInTerminal", tool_input={"command": FAILING}, tool_response="ok")
        raw["tool_use_id"] = "example"
    elif event == PROMPT_SUBMIT:
        raw["prompt"] = PROMPT
    elif event == SESSION_START:
        raw.update(source="new", model="claude-sonnet-4-6")
    elif event in (SUBAGENT_START, SUBAGENT_STOP):
        raw.update(agent_id="example", agent_type="Plan")
        if event == SUBAGENT_STOP:
            raw["stop_hook_active"] = False
    elif event == STOP:
        raw["stop_hook_active"] = False
    return raw


def _windsurf(event, vendor_event, base):
    """No file-write event exists here, so `pre_tool` is the shell command that would write."""
    raw = dict(base, hook_event_name=vendor_event)
    if event == PRE_TOOL:
        raw["tool_info"] = {"command_line": "echo '%s' >> %s" % (SECRET, MEMORY_FILE)}
    elif event == POST_TOOL:
        raw["tool_info"] = {"server": "docs", "tool": "fetch"}
        raw["output"] = "page text"
    elif event == PROMPT_SUBMIT:
        raw["query"] = PROMPT
    return raw


#: Vendors whose envelope is not Claude-shaped get their own builder.
SPECIAL = {"antigravity": _antigravity, "vscode_copilot": _vscode, "windsurf": _windsurf}


def payload(agent, event, vendor_event):
    """One payload for `agent` at `event`, where `vendor_event` is that agent's name for it."""
    base = BASES[agent]
    builder = SPECIAL.get(agent)
    if builder:
        return builder(event, vendor_event, base)
    return _claude_shaped(agent, event, vendor_event, base, camel=(agent == "grok"))
