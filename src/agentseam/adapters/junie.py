"""Junie CLI adapter.

The inherited matrix row said "a Junie CLI hook surface is reported but unverified". It has
one, and it is among the strongest here: `PreToolUse` returns `allow` / `ask` / `block` and
carries `updatedInput`, so all three of block, ask and rewrite are native -- no degradation.
Junie states outright that its field names follow Claude Code's wire protocol so a script
can be shared between the two.

That shared protocol is also the hazard: the event names ARE Claude Code's. `project_path`
is the separator -- Junie sends it, Claude Code does not -- so `claims()` requires it and
Claude Code's adapter declines a payload carrying it.

Three behaviours worth carrying into the notes because they change what a policy means:

  * **Project-local hooks are ignored by default.** `<project>/.junie/config.json` is
    repository-controlled, so Junie will not run shell commands from it without
    `--config-location`. A guardrail committed to a repo therefore does *not* take effect
    for a teammate who clones it -- the opposite of every other agent here, and the reason
    `CONFIG_PATH` points at the user file.
  * **PermissionRequest inverts the usual default.** A hook that exits 0 without a blocking
    decision *approves* the action and skips the dialog the user would otherwise have seen.
    Installing a handler there removes a confirmation step unless the handler is careful,
    so it is mapped but treated as a gate that must answer deliberately.
  * **StopFailure is observability-only** -- output and exit code are ignored -- and it
    fires on LLM/API failures, not tool failures, so it is not `tool_failure` and is left
    unmapped rather than bent into it.

Verified against Junie CLI's hooks documentation (2026-08-26).
"""

from __future__ import annotations

import json as _json

from ..contract import (
    ALLOW,
    ASK,
    DENY,
    PRE_TOOL,
    PROMPT_SUBMIT,
    REWRITE,
    SESSION_END,
    SESSION_START,
    STOP,
    UNKNOWN,
    Event,
)

AGENT = "junie"

EVENT_MAP = {
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "PreToolUse": PRE_TOOL,
    "PermissionRequest": PRE_TOOL,
    "Stop": STOP,
    # StopFailure fires on a classified LLM/API failure, not a tool failure -- the vendor
    # says a PostToolUseFailure hook is future work -- so mapping it to tool_failure would
    # be a different claim than the one it supports.
}
REVERSE_EVENT_MAP = {
    SESSION_START: "SessionStart",
    SESSION_END: "SessionEnd",
    PROMPT_SUBMIT: "UserPromptSubmit",
    PRE_TOOL: "PreToolUse",
    STOP: "Stop",
}

#: Junie sends this on session-scoped events; Claude Code, whose event names these are, does
#: not. Without it the two are indistinguishable.
MARKER = "project_path"

#: Events whose stdout is read. SessionEnd's output is documented as discarded entirely.
BLOCKING_EVENTS = ("UserPromptSubmit", "PreToolUse", "PermissionRequest", "Stop")


def claims(raw):
    if not isinstance(raw, dict):
        return False
    return raw.get("hook_event_name") in EVENT_MAP and MARKER in raw


def parse(raw):
    ti = raw.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
    # The docstring stakes everything on Junie's field names following Claude Code's wire
    # protocol exactly, so MultiEdit's edits[].new_string and NotebookEdit's new_source get
    # the same fallback chain claude_code.parse uses -- not a guess, a claim we already made.
    content = ti.get("content") or ti.get("new_string") or ti.get("new_source") or None
    if content is None and isinstance(ti.get("edits"), list):
        joined = "\n".join(str(e.get("new_string", "")) for e in ti["edits"])
        content = joined or None
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
        tool=raw.get("tool_name"),
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("path") or ti.get("notebook_path"),
        content=content,
        output=raw.get("last_assistant_message"),
        prompt=raw.get("prompt"),
        session_id=raw.get("session_id"),
        cwd=raw.get("cwd") or raw.get("project_path"),
        raw=raw,
    )


def respond(decision, event):
    name = (event.raw or {}).get("hook_event_name")
    if name not in BLOCKING_EVENTS:
        return "", 0

    if name == "Stop":
        # Stop speaks retry, not permission: a block feeds the reason back and the agent
        # tries again, bounded by JUNIE_STOP_HOOK_BLOCK_CAP.
        if decision.outcome in (DENY, ASK, REWRITE):
            return _json.dumps({"decision": "block", "reason": decision.reason or "not finished"}), 0
        return "", 0

    if decision.outcome == REWRITE and decision.updated_input is not None:
        body = {"decision": "allow", "updatedInput": decision.updated_input}
        if decision.reason:
            body["reason"] = decision.reason
        return _json.dumps(body), 0
    if decision.outcome == ASK:
        return _json.dumps({"decision": "ask", "reason": decision.reason or "confirmation required"}), 0
    if decision.outcome in (DENY, REWRITE):
        reason = decision.reason
        if decision.outcome == REWRITE:
            reason = "%s (no replacement input was supplied)" % (reason or "input requires modification")
        return _json.dumps({"decision": "deny", "reason": reason or "blocked by policy"}), 0

    # An explicit allow, deliberately: on PermissionRequest an empty success already
    # approves and skips the user's dialog, so silence here would be a decision too.
    body = {"decision": "allow"}
    if decision.outcome == ALLOW and decision.reason:
        body["additionalContext"] = decision.reason
    return _json.dumps(body), 0


def hook_config(canonical_events, command, matcher=None):
    """Junie's own user-level file.

    Not the project file: Junie ignores hooks in a repository-controlled config unless it is
    passed with --config-location, so writing there would produce a guardrail that silently
    does not run.
    """
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


#: Project-local hooks are ignored by default, so the user file is the only location that
#: takes effect without an explicit --config-location.
CONFIG_PATH = "~/.junie/config.json"
