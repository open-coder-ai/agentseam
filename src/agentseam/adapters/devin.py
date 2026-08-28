"""Devin CLI adapter.

Devin speaks Claude Code's hook format almost exactly: the same event names, the same
`{hook_event_name, tool_name, tool_input, session_id}` input, `hookSpecificOutput` with
`additionalContext` and `updatedInput`, and exit 2 to block. It even reads Claude Code's
own `.claude/settings.json` for hooks by default.

That similarity is the hazard. Two adapters claiming one payload makes `detect()` return
None, and a dispatcher that cannot name the agent allows the call it was installed to gate.
So detection here turns on the fields that actually differ:

  * Devin carries `prompt_id`, a per-turn id Claude Code has no equivalent of.
  * `PermissionRequest` and `PostCompaction` are Devin-only events. `PostCompaction` is left
    UNMAPPED rather than folded into canonical `PRE_COMPACT`: it fires AFTER compaction, so a
    handler wired there to flush or snapshot context -- the reason `pre_compact` exists --
    would run once the context it wanted to save is already discarded. `PreCompact` is a
    different moment Devin does not appear to expose at all.

**A Devin `SessionStart` payload is genuinely indistinguishable from Claude Code's**, because
`prompt_id` is documented as absent for events that fire before the first user prompt. Rather
than let a coin-flip decide, neither adapter claims it: `detect()` returns None and the
caller must name the agent. A test pins that, so the ambiguity stays visible instead of
turning into a wrong answer later.

Devin's response dialect differs from Claude Code's in one place worth care: a block is the
top-level `{"decision": "block"}`, not `hookSpecificOutput.permissionDecision`. There is no
"ask" in the vocabulary at all.

Verified against Devin's hooks documentation (2026-08-26).
"""

from __future__ import annotations

import json as _json

from ..contract import (
    ASK,
    DENY,
    POST_TOOL,
    PRE_TOOL,
    PROMPT_SUBMIT,
    REWRITE,
    SESSION_END,
    SESSION_START,
    STOP,
    UNKNOWN,
    Event,
    degraded_from,
)
from .claude_code import looks_like_claude_code

AGENT = "devin"

# PostCompaction is deliberately absent: it fires AFTER compaction, so folding it into
# canonical PRE_COMPACT would claim a "before" gate that is actually "after" -- see the
# module docstring. claims() still recognises the event name via _DEVIN_ONLY below; it just
# is not wired to any canonical event, so parse() reports it UNKNOWN rather than guess.
EVENT_MAP = {
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "PermissionRequest": PRE_TOOL,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "Stop": STOP,
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
}
REVERSE_EVENT_MAP = {
    PRE_TOOL: "PreToolUse",
    POST_TOOL: "PostToolUse",
    PROMPT_SUBMIT: "UserPromptSubmit",
    STOP: "Stop",
    SESSION_START: "SessionStart",
    SESSION_END: "SessionEnd",
}

#: Events Claude Code does not have. Seeing one is proof of Devin on its own.
_DEVIN_ONLY = ("PermissionRequest", "PostCompaction")

#: Events that inject context rather than gate anything.
_CONTEXT_EVENTS = ("UserPromptSubmit", "SessionStart", "PostToolUse")

# SHELL_TOOL = "exec" used to sit here, with a comment claiming it was "named here so
# Event.command is populated the same way as elsewhere". parse() never read it: command
# comes from tool_input like every other adapter. A constant that documents behaviour the
# code does not have is worse than no constant, because the next reader believes it.


def claims(raw):
    """True only when the payload is distinguishable from Claude Code's.

    Deliberately conservative: an ambiguous payload is claimed by nobody, so the dispatcher
    refuses to guess rather than picking one of two adapters that would answer differently.
    """
    if not isinstance(raw, dict):
        return False
    name = raw.get("hook_event_name")
    if name in _DEVIN_ONLY:
        return True
    # `prompt_id` was the whole discriminator, and it stopped being one: a live capture
    # showed Claude Code sending it on nearly every event, at which point this adapter
    # claimed 38 of 42 real Claude Code payloads and detect() handed them over without
    # ambiguity -- a deny then rendered in Devin's dialect, which Claude Code ignores.
    # So defer whenever a field we have actually observed from Claude Code is present.
    return name in EVENT_MAP and "prompt_id" in raw and not looks_like_claude_code(raw)


def parse(raw):
    ti = raw.get("tool_input") or {}
    content = ti.get("content") or ti.get("new_string") or None
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
        path=ti.get("file_path") or ti.get("path"),
        content=content,
        output=out,
        prompt=raw.get("prompt"),
        session_id=raw.get("session_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


#: Decision words this vendor accepts. No "ask" and no "deny": the pair is approve/block,
#: per the docstring above and the comment in respond().
DECISION_VOCABULARY = frozenset({"approve", "block"})


#: The events whose stdout decision is actually read. Everywhere else this row is
#: observation-only, and a verdict there is not a quieter refusal -- it is a refusal nobody
#: reads, which invites a log or a consumer to record a block that never happened. Until
#: 2026-08-28 respond() emitted {"decision": "block"} at post_tool, session_start and
#: session_end alike, contradicting this adapter's own matrix row.
#: PermissionRequest is here because it maps to canonical pre_tool, which the matrix rates
#: blocking -- leaving it out made a deny at a permission gate return silence, i.e. an
#: allow. A vendor event is in this tuple if the canonical event it maps to can block, not
#: if its name looks like a gate.
_BLOCKING_EVENTS = ("PreToolUse", "PermissionRequest", "UserPromptSubmit", "Stop")


def respond(decision, event):
    name = (event.raw or {}).get("hook_event_name") or "PreToolUse"

    if name not in _BLOCKING_EVENTS:
        # The finding is still worth recording where there is a channel for it. Silence
        # otherwise: SessionEnd has no additionalContext to carry it.
        if decision.reason and name in _CONTEXT_EVENTS:
            body = {"hookEventName": name, "additionalContext": decision.reason}
            return _json.dumps({"hookSpecificOutput": body}), 0
        return "", 0

    if decision.outcome == REWRITE:
        if name == "PreToolUse" and decision.updated_input is not None:
            # updatedInput is merged into the tool's arguments, so a partial object is
            # enough -- passing only the key that changed leaves the rest intact.
            body = {"hookEventName": "PreToolUse", "updatedInput": decision.updated_input}
            return _json.dumps({"hookSpecificOutput": body}), 0
        return _json.dumps(
            {"decision": "block", "reason": decision.reason or "input requires modification before it can run"}
        ), 0

    if decision.outcome in (DENY, ASK):
        # Devin has no "ask": the vocabulary is approve or block. Blocking with the reason
        # is the honest translation, because allowing through would be the opposite of
        # what a request for confirmation meant.
        reason = decision.reason or "blocked by policy"
        if decision.outcome == ASK:
            note = (
                "Devin cannot modify a tool call"
                if degraded_from(decision) == REWRITE
                else "Devin cannot prompt for confirmation"
            )
            reason = "%s (%s, so this is a block)" % (reason, note)
        return _json.dumps({"decision": "block", "reason": reason}), 0

    if decision.reason and name in _CONTEXT_EVENTS:
        body = {"hookEventName": name, "additionalContext": decision.reason}
        return _json.dumps({"hookSpecificOutput": body}), 0
    return _json.dumps({"decision": "approve"}), 0


def hook_config(canonical_events, command, matcher=None):
    """Devin's own file. `.devin/hooks.v1.json` holds the hooks object as the whole file.

    Devin also reads `.claude/settings.json`, but writing there would put our entry in
    another agent's config, where an uninstall could not tell the two apart.
    """
    config = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        entry = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            entry["matcher"] = matcher
        config.setdefault(name, []).append(entry)
    return config


CONFIG_PATH = ".devin/hooks.v1.json"
