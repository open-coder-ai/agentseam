"""OpenAI Codex CLI adapter.

Verified against the vendor's generated schemas and hook engine source (openai/codex:
codex-rs/hooks/src/schema.rs, engine/output_parser.rs, engine/discovery.rs,
app-server-protocol/schema/typescript/v2/HookEventName.ts).

Codex speaks the Claude-family decision shape — hookSpecificOutput.permissionDecision
with allow/deny/ask — but names its events in camelCase and adds turn-scoped fields
(turn_id, model, permission_mode) that Claude Code does not send. Those extra fields
are how an adapter tells the two apart when the payload is otherwise identical.
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
    SUBAGENT_START,
    SUBAGENT_STOP,
    Event,
)

AGENT = "codex_cli"

# HookEventName.ts, verbatim. camelCase, unlike Claude Code's PascalCase.
EVENT_MAP = {
    "preToolUse": PRE_TOOL,
    "postToolUse": POST_TOOL,
    "userPromptSubmit": PROMPT_SUBMIT,
    "sessionStart": SESSION_START,
    "sessionEnd": SESSION_END,
    "preCompact": PRE_COMPACT,
    "stop": STOP,
    "subagentStart": SUBAGENT_START,
    "subagentStop": SUBAGENT_STOP,
    # permissionRequest, postCompact and interrupt have no canonical counterpart yet;
    # leaving them unmapped keeps the matrix honest rather than inventing coverage.
}
REVERSE_EVENT_MAP = {v: k for k, v in EVENT_MAP.items()}


def claims(raw):
    """Codex's PreToolUse carries turn_id and permission_mode; Claude Code's does not."""
    if not isinstance(raw, dict):
        return False
    if raw.get("hook_event_name") not in EVENT_MAP:
        return False
    return "turn_id" in raw or "permission_mode" in raw or "model" in raw


def parse(raw):
    ti = raw.get("tool_input") or {}
    if not isinstance(ti, dict):
        ti = {}
    content = ti.get("content") or ti.get("new_string") or ti.get("new_str")
    if content is None and isinstance(ti.get("edits"), list):
        content = "\n".join(str(e.get("new_string", "")) for e in ti["edits"]) or None
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hook_event_name")),
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


def respond(decision, event):
    """Always exit 0 and carry the verdict in JSON.

    Codex wraps hook commands in `powershell -Command` on Windows, which collapses
    exit 2 into exit 1 -- so an exit-code deny is silently downgraded to "the hook
    errored" on one platform. The JSON decision is the only representation that means
    the same thing everywhere.
    """
    import json as _json

    out = {"hookEventName": REVERSE_EVENT_MAP.get(event.event, "preToolUse")}
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
    """ConfiguredHookMatcherGroup shape: {matcher, hooks: [{type: command, ...}]}."""
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


CONFIG_PATH = ".codex/hooks.json"
