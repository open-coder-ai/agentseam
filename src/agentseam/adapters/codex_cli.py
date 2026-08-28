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

# Re-exported: callers and tests address this through the adapter that needs it, and the
# rule it encodes is a PowerShell fact two vendors share. See _windows.py.
from ._windows import powershell_command  # noqa: E402,F401

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


#: SessionStartCommandInput's fields, minus the event name. The struct is
#: deny_unknown_fields, so this is the whole payload -- there is nothing else to match on.
_SESSION_START_FIELDS = ("session_id", "transcript_path", "cwd", "model", "permission_mode", "source")


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

    SessionStart is the exception, and it is claimed on shape instead. It is not
    turn-scoped, so Codex sends no turn_id there -- confirmed live (2026-08-28) and by
    `SessionStartCommandInput`, which is `deny_unknown_fields` and defines exactly the six
    fields below plus the event name. Every one of them is a field Claude Code also sends,
    so nothing here can tell the two apart. Claiming it anyway makes `detect()` DECLINE as
    ambiguous, which is the honest answer: before this, a real Codex SessionStart was
    claimed by claude_code alone and answered confidently in the wrong dialect, which Codex
    rejects (its output structs are deny_unknown_fields) and therefore fails open. Naming
    the agent explicitly is how a consumer resolves it, the same as tabnine and gemini_cli.
    """
    if not isinstance(raw, dict):
        return False
    name = raw.get("hook_event_name")
    if name not in EVENT_MAP:
        return False
    if "turn_id" in raw:
        return True
    return name == "SessionStart" and all(field in raw for field in _SESSION_START_FIELDS)


def parse(raw):
    """Normalise one payload.

    **A Codex write does not arrive with a path or content.** Live capture (2026-08-28, 36
    payloads) observed exactly two tool names -- `Bash` and `apply_patch` -- and BOTH carry
    only `tool_input.command`. `apply_patch` is the file-writing tool, and the patch text
    rides inside that command string. So on this agent a content policy has to gate on
    `event.command`; `event.content` and `event.path` stay None for a real write, and a
    handler written as `"SECRET" in (event.content or "")` will not fire here.

    `new_string`, `new_str` and `edits` used to be read alongside them. That was Claude
    Code's MultiEdit vocabulary copied across on the assumption Codex shared it; Codex has
    no such tool, and no payload has ever carried those keys. Removed rather than left to
    imply a coverage this adapter does not have. `content`/`file_path`/`path` are kept only
    as a generic fallback for MCP tools, whose tool_input this capture did not exercise.
    """
    ti = raw.get("tool_input") or {}
    if not isinstance(ti, dict):
        ti = {}
    content = ti.get("content")
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


#: The two events whose refusal is a top-level {"decision": "block", "reason": ...} rather
#: than the PreToolUse permissionDecision gate. Their output structs
#: (UserPromptSubmitCommandOutputWire, StopCommandOutputWire) carry `decision:
#: BlockDecisionWire` -- whose ONLY value is "block" -- and no permissionDecision field at
#: all. Matches the matrix row: pre_tool, prompt_submit and stop are the blocking events.
_BLOCK_DIALECT_EVENTS = (PROMPT_SUBMIT, STOP)


#: Decision words this vendor HONOURS. "ask" is deliberately absent: it is in schema.rs's
#: PreToolUsePermissionDecisionWire, but output_parser.rs rejects it as an unsupported
#: response -- and a rejected response fails open, so emitting it would be worse than a deny.
DECISION_VOCABULARY = frozenset({"allow", "deny", "block"})


def respond(decision, event):
    """Always exit 0 and carry the verdict in JSON, in the dialect THIS event accepts.

    Codex wraps hook commands in `powershell -Command` on Windows, which collapses exit 2
    into exit 1 -- so an exit-code deny is silently downgraded to "the hook errored" on one
    platform. The JSON decision is the only representation that means the same thing
    everywhere.

    Every per-event output struct in hooks/src/schema.rs is `#[serde(deny_unknown_fields)]`,
    so a key that event does not define is not ignored: Codex rejects the whole response.
    Witnessed live (Codex CLI 0.150.1, 2026-08-28): sending the PreToolUse
    permissionDecision shape at UserPromptSubmit produced "hook returned invalid user prompt
    submit JSON output" on every prompt. Three dialects, one per group of events:

      * PRE_TOOL -- hookSpecificOutput.permissionDecision (deny, or allow WITH updatedInput)
      * PROMPT_SUBMIT / STOP -- top-level {"decision": "block", "reason": ...}
      * everything else -- no decision surface exists, so silence

    A bare allow is silence everywhere, including at PRE_TOOL: output_parser.rs's
    `unsupported_pre_tool_use_hook_specific_output` rejects permissionDecision:allow unless
    it carries updatedInput, and a rejected response is a hook error, which fails OPEN. An
    empty stdout is how this adapter says "no opinion", and it is the only spelling of allow
    Codex accepts at every event.
    """
    import json as _json

    if event.event == PRE_TOOL:
        return _pre_tool_response(decision)
    if event.event in _BLOCK_DIALECT_EVENTS:
        if decision.outcome in (DENY, ASK, REWRITE):
            return _json.dumps({"decision": "block", "reason": _refusal_reason(decision)}), 0
        return "", 0
    # Observation-only events. Codex defines no decision field for them (SessionEnd has no
    # output struct at all), so a verdict here would be rejected, not merely ignored.
    return "", 0


def _refusal_reason(decision):
    """The reason text for a refusal, annotated when the decision had to be degraded."""
    if decision.outcome == ASK:
        return _because(decision.reason, "Codex CLI cannot prompt for confirmation at this event")
    if decision.outcome == REWRITE:
        return _because(decision.reason, "Codex CLI cannot modify a tool call at this event")
    return decision.reason or "blocked by policy"


def _pre_tool_response(decision):
    """The permissionDecision gate, the one place Codex reads a permission verdict."""
    import json as _json

    out = {"hookEventName": "PreToolUse"}
    if decision.outcome == REWRITE and decision.updated_input is not None:
        # The only accepted spelling of allow: it must carry updatedInput.
        out["permissionDecision"] = "allow"
        out["updatedInput"] = decision.updated_input
        if decision.reason:
            out["permissionDecisionReason"] = decision.reason
    elif decision.outcome in (DENY, ASK, REWRITE):
        # ASK is rejected by Codex's own parser as an unsupported permissionDecision, and a
        # rejected response fails OPEN -- so asking would silently permit the very call the
        # handler wanted confirmed. A REWRITE with nothing to substitute is the same story.
        out["permissionDecision"] = "deny"
        note = None
        if decision.outcome == ASK:
            note = "Codex CLI does not support ask; asking would fail open"
        elif decision.outcome == REWRITE:
            note = "Codex CLI cannot apply a rewrite with no updatedInput"
        out["permissionDecisionReason"] = _because(decision.reason, note) if note else (decision.reason or "blocked")
    else:
        return "", 0  # allow: silence, since permissionDecision:allow alone is rejected
    return _json.dumps({"hookSpecificOutput": out}), 0


def hook_config(canonical_events, command, matcher=None):
    """ConfiguredHookMatcherGroup shape: {matcher, hooks: [{type: command, ...}]}.

    `commandWindows` is Codex's own per-platform override (HookHandlerConfig::Command in
    config/src/hook_config.rs; discovery.rs prefers it over `command` when cfg!(windows)).
    Using it keeps `command` as the POSIX form -- the exact interpreter that installed the
    hook, quoted -- while Windows gets the PowerShell-callable spelling, rather than trading
    a verified interpreter path for a bare `python3` and hoping PATH resolves it.
    """
    hooks = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        entry = {"hooks": [{"type": "command", "command": command, "commandWindows": powershell_command(command)}]}
        if matcher:
            entry["matcher"] = matcher
        hooks.setdefault(name, []).append(entry)
    return {"hooks": hooks}


CONFIG_PATH = ".codex/hooks.json"
