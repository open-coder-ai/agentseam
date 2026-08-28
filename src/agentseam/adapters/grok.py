"""Grok CLI adapter.

Claude Code's event *names* in Claude Code's config *shape*, but with camelCase payload
*fields*: `hookEventName`, `sessionId`, `toolName`, `toolInput`, `cwd`, `workspaceRoot`.
That combination -- PascalCase event values under a camelCase key -- is unique among the
agents here, and it is what `claims()` keys on. Claude Code sends `hook_event_name`; VS
Code Copilot and Codex send `hookEventName` with camelCase *values* like `preToolUse`.

Two limits worth stating plainly:

  * **PreToolUse is the only blocking event.** Everything else is passive: stdout is
    ignored, and a decision returned there changes nothing.
  * **No rewrite.** The response vocabulary is `{"decision": "deny", "reason": ...}` and
    nothing else, so a rewrite has no expression and the dispatcher degrades it.

Failures fail **open**: timeouts, crashes and malformed output are recorded in the session
and the tool call proceeds. Only an explicit deny (or exit 2) blocks.

Grok also reads Claude Code's `.claude/settings.json` and Cursor's `.cursor/hooks.json`,
Cursor's camelCase event names included -- so a repo wired for either is already running
those hooks under Grok.

Verified against Grok's hooks documentation (2026-08-26).
"""

from __future__ import annotations

import json as _json

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
    UNKNOWN,
    Event,
    degraded_from,
)

AGENT = "grok"

EVENT_MAP = {
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "PostToolUseFailure": TOOL_FAILURE,
    "PermissionDenied": TOOL_FAILURE,
    "Stop": STOP,
    "StopFailure": STOP,
    "SubagentStart": SUBAGENT_START,
    "SubagentStop": SUBAGENT_STOP,
    "PreCompact": PRE_COMPACT,
    "PostCompact": PRE_COMPACT,
}
REVERSE_EVENT_MAP = {
    SESSION_START: "SessionStart",
    SESSION_END: "SessionEnd",
    PROMPT_SUBMIT: "UserPromptSubmit",
    PRE_TOOL: "PreToolUse",
    POST_TOOL: "PostToolUse",
    TOOL_FAILURE: "PostToolUseFailure",
    STOP: "Stop",
    SUBAGENT_START: "SubagentStart",
    SUBAGENT_STOP: "SubagentStop",
    PRE_COMPACT: "PreCompact",
}

#: The one event whose stdout is read. Everywhere else a decision is ignored, and saying
#: so beats returning JSON that looks like it did something.
BLOCKING_EVENT = "PreToolUse"


def claims(raw):
    """camelCase `hookEventName` carrying a PascalCase value is Grok's alone.

    Claude Code spells the key `hook_event_name`; Codex and VS Code Copilot use this key
    with camelCase values (`preToolUse`). Requiring both halves keeps all four apart.
    """
    if not isinstance(raw, dict):
        return False
    return raw.get("hookEventName") in EVENT_MAP


def parse(raw):
    ti = raw.get("toolInput")
    ti = ti if isinstance(ti, dict) else {}
    content = ti.get("content") or ti.get("new_string") or None
    out = raw.get("toolOutput")
    if isinstance(out, (dict, list)):
        out = _json.dumps(out)
    return Event(
        AGENT,
        # An event this adapter has no mapping for resolves to UNKNOWN, never to the
        # nearest canonical one: relabelling it invites a guardrail to evaluate the
        # wrong policy against it.
        EVENT_MAP.get(raw.get("hookEventName"), UNKNOWN),
        tool=raw.get("toolName"),
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("path"),
        content=content,
        output=out,
        prompt=raw.get("prompt"),
        session_id=raw.get("sessionId"),
        cwd=raw.get("cwd") or raw.get("workspaceRoot"),
        raw=raw,
    )


#: Decision words this vendor accepts. Exactly one: the documented vocabulary is
#: {decision: deny, reason} and nothing more -- no allow verb, no ask, no rewrite.
DECISION_VOCABULARY = frozenset({"deny"})


def respond(decision, event):
    name = (event.raw or {}).get("hookEventName")
    if name != BLOCKING_EVENT:
        # Passive event: stdout is ignored. Emitting a decision would imply a gate.
        return "", 0

    if decision.outcome == REWRITE:
        # No updatedInput equivalent. Allowing the unmodified input through is the one
        # reading that is certainly wrong, so this denies and says why.
        return _json.dumps(
            {"decision": "deny", "reason": _because(decision.reason, "Grok cannot modify a tool call")}
        ), 0
    if decision.outcome == ASK:
        # Read what this was *before* the dispatcher reduced it: a rewrite that became an
        # ask and is now a block was never a request for confirmation.
        note = (
            "Grok cannot modify a tool call"
            if degraded_from(decision) == REWRITE
            else "Grok cannot prompt for confirmation"
        )
        return _json.dumps({"decision": "deny", "reason": _because(decision.reason, note)}), 0
    if decision.outcome == DENY:
        return _json.dumps({"decision": "deny", "reason": decision.reason or "blocked by policy"}), 0
    return "", 0  # exit 0 allows; there is no explicit allow verb


def _because(reason, note):
    """Keep the handler's reason and add why the outcome changed shape."""
    return "%s (%s)" % (reason, note) if reason else note


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


#: Project hooks require trust before they run: `/hooks-trust`, or launching with --trust.
#: Installing the file is therefore not the whole job, and `doctor` saying "wired" here
#: means the config is present, not that Grok has been allowed to run it.
NEEDS_TRUST = True

CONFIG_PATH = ".grok/hooks/agentseam.json"
