"""OpenAI Codex CLI adapter.

Verified against the vendor's hook engine source (openai/codex: config/src/hook_config.rs,
hooks/src/schema.rs, hooks/src/engine/output_parser.rs, hooks/src/engine/discovery.rs).

Codex speaks the Claude-family decision shape — hookSpecificOutput.permissionDecision with
allow/deny — and names its events in PASCALCASE, the same convention Claude Code uses:
`HookEventsToml`'s field renames in hook_config.rs ("PreToolUse", "PostToolUse", ...) are
what a hooks.json config file's event keys must match, and `HookEventNameWire`'s literal
constructions in schema.rs (`hook_event_name: "PreToolUse".to_string()`) confirm the same
casing on the runtime wire payload's own `hook_event_name` field. A previous version of this
adapter believed the events were camelCase, sourced from
app-server-protocol/schema/typescript/v2/HookEventName.ts -- that file is a ts-rs binding for
the App Server's separate IDE-facing JSON-RPC protocol, not the plain CLI hook-subprocess
dialect this adapter speaks; the two use different casing for the same event names.

Codex adds a turn-scoped `turn_id` field that Claude Code does not send -- the one field
that tells the two apart when the payload's event names are otherwise identical, since real
Claude Code event names are PascalCase too. `permission_mode` and `model` were both believed
exclusive to Codex at one point and both turned out to be shared (with Claude Code and Cursor
respectively); see `claims()`'s docstring.

"ask" is a rejected permissionDecision value at PreToolUse, per output_parser.rs's own
`unsupported_pre_tool_use_hook_specific_output`: Codex treats it as an invalid hook response
(not a real prompt), which Codex then handles by failing OPEN -- so `respond()` degrades ASK
to DENY with an explanatory reason there rather than emit a value the vendor's own parser
rejects.
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
    UNKNOWN,
    Event,
)

AGENT = "codex_cli"

# hook_config.rs's HookEventsToml field renames, and schema.rs's HookEventNameWire /
# literal hook_event_name construction -- both PascalCase, matching Claude Code's own.
EVENT_MAP = {
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "PreCompact": PRE_COMPACT,
    "Stop": STOP,
    "SubagentStart": SUBAGENT_START,
    "SubagentStop": SUBAGENT_STOP,
    # PermissionRequest, PostCompact and Interrupt have no canonical counterpart yet;
    # leaving them unmapped keeps the matrix honest rather than inventing coverage.
}
REVERSE_EVENT_MAP = {v: k for k, v in EVENT_MAP.items()}


def claims(raw):
    """Codex's PreToolUse carries turn_id; Claude Code's does not.

    `model` used to count as a second marker and no longer does: Cursor's base hook schema
    sends `model` on every event, so claiming on it made every real Cursor payload
    ambiguous between the two adapters -- and an unidentified payload is allowed through.
    `permission_mode` used to count as a marker here too and no longer does either: a real
    live-captured Claude Code payload (2026-08-27, PreToolUse) carries `permission_mode`
    too -- confirmed once EVENT_MAP's casing was fixed to the vendor's actual PascalCase and
    codex_cli started claiming real Claude Code traffic that only `permission_mode` matched
    on. Two fields once believed exclusive to Codex have both turned out to be shared;
    `turn_id` is the one still unrefuted by a real captured payload.
    """
    if not isinstance(raw, dict):
        return False
    if raw.get("hook_event_name") not in EVENT_MAP:
        return False
    return "turn_id" in raw


def parse(raw):
    ti = raw.get("tool_input") or {}
    if not isinstance(ti, dict):
        ti = {}
    content = ti.get("content") or ti.get("new_string") or ti.get("new_str")
    if content is None and isinstance(ti.get("edits"), list):
        content = "\n".join(str(e.get("new_string", "")) for e in ti["edits"]) or None
    return Event(
        AGENT,
        # An event this adapter has no mapping for resolves to UNKNOWN, never to the
        # nearest canonical one: relabelling it invites a guardrail to evaluate the
        # wrong policy against it.
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
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


def _because(reason, note):
    return "%s (%s)" % (reason, note) if reason else note


def respond(decision, event):
    """Always exit 0 and carry the verdict in JSON.

    Codex wraps hook commands in `powershell -Command` on Windows, which collapses
    exit 2 into exit 1 -- so an exit-code deny is silently downgraded to "the hook
    errored" on one platform. The JSON decision is the only representation that means
    the same thing everywhere.
    """
    import json as _json

    out = {"hookEventName": REVERSE_EVENT_MAP.get(event.event, "PreToolUse")}
    if decision.outcome == DENY:
        out["permissionDecision"] = "deny"
        out["permissionDecisionReason"] = decision.reason or "blocked"
    elif decision.outcome == ASK:
        # Not a degradation of our own contract: Codex's own PreToolUse output parser
        # rejects permissionDecision:ask as an invalid hook response (unsupported), which
        # Codex then treats as a hook error -- and hook errors fail OPEN. Emitting "ask"
        # here would silently let through exactly what the handler wanted confirmed.
        out["permissionDecision"] = "deny"
        out["permissionDecisionReason"] = _because(
            decision.reason, "Codex CLI does not support ask; asking would fail open"
        )
    elif decision.outcome == REWRITE:
        out["permissionDecision"] = "allow"
        out["updatedInput"] = decision.updated_input
        if decision.reason:
            out["permissionDecisionReason"] = decision.reason
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
