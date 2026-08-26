"""Gemini CLI adapter.

Verified against the vendor's own hooks reference (docs/hooks/reference.md in
google-gemini/gemini-cli). Notable differences from the Claude-family contract:

  * events are Before*/After*, not Pre*/Post*
  * the decision field is `decision: "allow" | "deny"` at the TOP level, with
    `reason` — not nested under hookSpecificOutput
  * a rewrite is `hookSpecificOutput.tool_input`, which MERGES WITH and overrides
    the model's arguments rather than replacing them wholesale
  * exit code 2 also blocks, using stderr as the reason
  * write tools are named write_file / replace, not Write / Edit
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
    Event,
)

AGENT = "gemini_cli"

EVENT_MAP = {
    "BeforeTool": PRE_TOOL,
    "AfterTool": POST_TOOL,
    "BeforeAgent": PROMPT_SUBMIT,
    "AfterAgent": STOP,
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "PreCompress": PRE_COMPACT,
}
REVERSE_EVENT_MAP = {
    PRE_TOOL: "BeforeTool",
    POST_TOOL: "AfterTool",
    PROMPT_SUBMIT: "BeforeAgent",
    STOP: "AfterAgent",
    SESSION_START: "SessionStart",
    SESSION_END: "SessionEnd",
    PRE_COMPACT: "PreCompress",
}

# Gemini's file-writing tools. `replace` is an edit; `write_file` is a whole-file write.
WRITE_TOOLS = ("write_file", "replace")
# Its shell tool carries the command under a different key than the Claude family.
SHELL_TOOLS = ("run_shell_command",)


#: Agents that name themselves in the payload. A payload naming a different client is not
#: ours, whatever its event is called -- SessionStart and SessionEnd are spelled the same
#: way by Claude Code, Devin and Kimi Code, and only Kimi carries proof of which it is.
#: Claude Code's adapter applies the same rule; the general form is that a positive
#: self-identification beats a shared event name.
_OWN_CLIENT_TYPES = (None, "gemini_cli", "gemini")


def claims(raw):
    if not isinstance(raw, dict) or raw.get("hook_event_name") not in EVENT_MAP:
        return False
    return raw.get("client_type") in _OWN_CLIENT_TYPES


def parse(raw):
    ti = raw.get("tool_input") or {}
    tool = raw.get("tool_name")
    content = None
    if tool in WRITE_TOOLS:
        # write_file uses `content`; replace supplies the replacement text.
        content = ti.get("content") or ti.get("new_string") or ti.get("new_str")
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hook_event_name")),
        tool=tool,
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("absolute_path") or ti.get("path"),
        content=content,
        output=raw.get("tool_output") or raw.get("tool_response"),
        prompt=raw.get("prompt") or raw.get("user_message"),
        session_id=raw.get("session_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def respond(decision, event):
    import json as _json

    if decision.outcome == DENY:
        # `reason` is required on a deny and is delivered TO THE AGENT as a tool
        # error, so it should read as an instruction the model can act on.
        return _json.dumps({"decision": "deny", "reason": decision.reason or "blocked by policy"}), 0
    if decision.outcome == ASK:
        # Gemini has no interactive confirmation in the hook protocol. Denying with an
        # explanation is the honest translation: never silently allow something the
        # handler wanted a human to see.
        return (
            _json.dumps(
                {
                    "decision": "deny",
                    "reason": "%s (confirmation required; this agent cannot prompt from a hook)"
                    % (decision.reason or "policy requires confirmation"),
                }
            ),
            0,
        )
    if decision.outcome == REWRITE:
        return _json.dumps({"hookSpecificOutput": {"tool_input": decision.updated_input}}), 0
    return _json.dumps({"decision": "allow"}), 0


def hook_config(canonical_events, command, matcher=None):
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


CONFIG_PATH = ".gemini/settings.json"
