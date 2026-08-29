"""Kimi Code CLI adapter.

The inherited matrix row for this agent said "No user hooks. Only declarative
agent.tool_permissions rules. No deny path for an external handler." All three clauses are
false: it has a twenty-event hook system, three of whose events block, and it accepts
Claude Code's own `hookSpecificOutput.permissionDecision` shape on stdout.

Two things set it apart from the other Claude-shaped agents:

  * **The config is TOML, not JSON** -- an `[[hooks]]` array of tables in
    `~/.kimi-code/config.toml`, and only four fields per entry (`event`, `matcher`,
    `command`, `timeout`); an extra field makes the whole file fail to load. That file also
    holds the user's other settings, so installation appends a marker-delimited block
    rather than rewriting the document.
  * **`client_type` names the agent in every payload.** Without it a Kimi payload is
    Claude Code's exactly -- same PascalCase event names, same snake_case fields, same
    `tool_input` -- so this field is the only thing keeping the two apart.

Only `PreToolUse`, `UserPromptSubmit` and `Stop` block. Everything else is documented as
fire-and-forget: the main flow proceeds regardless of what the script returns, so the
adapter stays silent there instead of emitting a decision that reads like a gate.

Fails **open**, and the vendor says so plainly enough to repeat: hooks here suit alerts and
lightweight interception, not a sole security barrier. Any exit code other than 2 allows.

Verified against Kimi Code CLI's hooks documentation (2026-08-26).
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
    tool_input_of,
)

AGENT = "kimi_code"

#: Every payload carries this. It is the whole of our detection, because the rest of the
#: envelope is indistinguishable from Claude Code's.
CLIENT_TYPE = "kimi_code_cli"

EVENT_MAP = {
    "UserPromptSubmit": PROMPT_SUBMIT,
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "PostToolUseFailure": TOOL_FAILURE,
    "PermissionResult": POST_TOOL,
    "Stop": STOP,
    # UNKNOWN, deliberately. These four are fire-and-forget per the vendor -- they are not
    # in BLOCKING_EVENTS -- but they used to map onto prompt_submit, pre_tool and stop,
    # which the matrix rates blocking. So `can_block("kimi_code", "prompt_submit")` said
    # True, a handler denied a prompt-injection attempt at a UserPromptQueued payload, and
    # respond() dropped it in silence: a gate that reported a block and permitted the act.
    #
    # Resolving them to UNKNOWN keeps what is true and drops what is not. claims() still
    # identifies these payloads (the name is still a key here), so a consumer is not blinded
    # to the moment; parse() just refuses to relabel a fire-and-forget event as a gate, and
    # no policy keyed to a canonical event fires on one.
    "UserPromptQueued": UNKNOWN,
    "PermissionRequest": UNKNOWN,
    "StopFailure": UNKNOWN,
    "Interrupt": UNKNOWN,
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "SubagentStart": SUBAGENT_START,
    "SubagentStop": SUBAGENT_STOP,
    "PreCompact": PRE_COMPACT,
    "PostCompact": PRE_COMPACT,
    # TurnStarted, TaskStarted, SessionHeartbeat and Notification have no canonical
    # counterpart; leaving them unmapped beats inventing coverage for them.
}
REVERSE_EVENT_MAP = {
    PROMPT_SUBMIT: "UserPromptSubmit",
    PRE_TOOL: "PreToolUse",
    POST_TOOL: "PostToolUse",
    TOOL_FAILURE: "PostToolUseFailure",
    STOP: "Stop",
    SESSION_START: "SessionStart",
    SESSION_END: "SessionEnd",
    SUBAGENT_START: "SubagentStart",
    SUBAGENT_STOP: "SubagentStop",
    PRE_COMPACT: "PreCompact",
}

#: The only events whose return value reaches the main flow. Documented, not inferred.
BLOCKING_EVENTS = ("PreToolUse", "UserPromptSubmit", "Stop")


def claims(raw):
    if not isinstance(raw, dict):
        return False
    return raw.get("client_type") == CLIENT_TYPE and raw.get("hook_event_name") in EVENT_MAP


def parse(raw):
    ti = raw.get("tool_input")
    ti = tool_input_of(ti)
    # The docstring stakes everything on this envelope being Claude Code's exactly (same
    # tool_input), so MultiEdit's edits[].new_string and NotebookEdit's new_source get the
    # same fallback chain claude_code.parse uses -- not a guess, a claim we already made.
    content = ti.get("content") or ti.get("new_string") or ti.get("new_source") or None
    if content is None and isinstance(ti.get("edits"), list):
        joined = "\n".join(str(e.get("new_string", "")) for e in ti["edits"] if isinstance(e, dict))
        content = joined or None
    out = raw.get("tool_output")
    if isinstance(out, (dict, list)):
        out = _json.dumps(out)
    return Event(
        AGENT,
        # An event this adapter has no mapping for resolves to UNKNOWN, never to the
        # nearest canonical one: relabelling it invites a guardrail to evaluate the
        # wrong policy against it.
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
        tool=raw.get("tool_name"),
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("path") or ti.get("notebook_path"),
        content=content,
        output=out,
        prompt=raw.get("prompt"),
        session_id=raw.get("session_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def _because(reason, note):
    return "%s (%s)" % (reason, note) if reason else note


#: Decision words this vendor accepts: Claude Code's permissionDecision vocabulary, which
#: this agent takes wholesale (see the note). Only "deny" is ever emitted here.
DECISION_VOCABULARY = frozenset({"allow", "deny", "ask"})


def respond(decision, event):
    name = (event.raw or {}).get("hook_event_name")
    if name not in BLOCKING_EVENTS:
        # Fire-and-forget event: the main flow proceeds whatever we return.
        return "", 0

    reason = decision.reason
    if decision.outcome == REWRITE:
        reason = _because(reason, "Kimi Code cannot modify a tool call")
    elif decision.outcome == ASK:
        note = (
            "Kimi Code cannot modify a tool call"
            if degraded_from(decision) == REWRITE
            else "Kimi Code cannot prompt for confirmation"
        )
        reason = _because(reason, note)
    elif decision.outcome != DENY:
        return "", 0

    # hookEventName included: the recorded claim is that Kimi takes Claude Code's
    # hookSpecificOutput shape, and Claude Code's carries it. Omitting a field from a shape
    # we say we are copying is an unforced difference from the thing we claim to be.
    body = {
        "hookEventName": name,
        "permissionDecision": "deny",
        "permissionDecisionReason": reason or "blocked by policy",
    }
    # Exit 2 also blocks and is the documented path, but the JSON form carries the reason
    # back into the model's context, which exit-code-only blocking does not.
    return _json.dumps({"hookSpecificOutput": body}), 0


CONFIG_PATH = "~/.kimi-code/config.toml"

#: install() writes a marker-delimited block instead of rewriting the document, because
#: this file is the user's whole CLI configuration rather than a hooks file.
CONFIG_FORMAT = "toml"


def hook_config(canonical_events, command, matcher=None):
    """The `[[hooks]]` entries, as data. `render_config` turns them into TOML text."""
    rules = []
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        rule = {"event": name, "command": command}
        if matcher:
            rule["matcher"] = matcher
        rules.append(rule)
    return rules


def _toml_value(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % escaped


def render_config(rules):
    """Emit `[[hooks]]` tables. Only the four documented fields, in a documented order.

    A fifth field would not merely be ignored -- Kimi Code refuses to load the whole config
    file -- so this deliberately cannot emit one.
    """
    blocks = []
    for rule in rules:
        lines = ["[[hooks]]"]
        for key in ("event", "matcher", "command", "timeout"):
            if rule.get(key) is not None:
                lines.append("%s = %s" % (key, _toml_value(rule[key])))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"
