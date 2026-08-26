"""Antigravity adapter.

Two things make this one different from every other adapter here.

**The payload does not name its event.** There is no `hookEventName` field, so the event has
to be inferred from shape. That inference has a genuine ambiguity in it: PreToolUse and
PostToolUse carry the same `toolCall` and `stepIdx`, separated only by PostToolUse's `error`
field, which is documented as empty rather than absent on success. So the tie is broken
*toward* PRE_TOOL, deliberately. Guessing post-tool on a pre-tool payload would skip the gate
and let the call through; guessing pre-tool on a post-tool payload only produces a decision
that Antigravity ignores, because PostToolUse output is `{}`. One direction fails open, the
other fails harmlessly.

`PreInvocation` and `PostInvocation` are left unmapped for the same reason taken to its
conclusion: their payloads are documented as *identical*, so nothing could tell them apart,
and neither has a canonical counterpart worth bending one into.

**The decision vocabulary is richer than ours.** PreToolUse accepts `allow`, `deny`, `ask`,
`force_ask` and `deny_unless_prior_grant`. agentseam's contract has three of those, so the
last two are reachable only by a handler writing Antigravity's dialect directly -- recorded
here rather than quietly dropped. `ask` is honoured, but respects a user's "Always Allow";
`force_ask` is the one that ignores cached permissions, and a handler that means "prompt
every time" is not getting it through this contract today.

Tool arguments are PascalCase (`CommandLine`, `TargetFile`, `CodeContent`), which is why the
field extraction below is explicit rather than a generic lookup.

Verified against Antigravity's hooks documentation (2026-08-26).
"""

from __future__ import annotations

import json as _json

from ..contract import ASK, DENY, POST_TOOL, PRE_TOOL, REWRITE, STOP, UNKNOWN, Event, degraded_from

AGENT = "antigravity"

#: Canonical -> the event key used in hooks.json.
REVERSE_EVENT_MAP = {PRE_TOOL: "PreToolUse", POST_TOOL: "PostToolUse", STOP: "Stop"}

#: Per-tool argument names. Antigravity's tools take PascalCase args that differ by tool,
#: so a guardrail asking "which file, what content" needs this table to get an answer.
_COMMAND_ARG = "CommandLine"
_PATH_ARGS = ("TargetFile", "AbsolutePath")
_CONTENT_ARGS = ("CodeContent", "ReplacementContent")


def claims(raw):
    """Structural: `conversationId` with `workspacePaths` is Antigravity's own envelope.

    Cursor's near-equivalents are `conversation_id` and `workspace_roots`, so the two do not
    collide. No event name is checked because the payload does not carry one.
    """
    if not isinstance(raw, dict):
        return False
    return "conversationId" in raw and isinstance(raw.get("workspacePaths"), list)


def _infer_event(raw):
    """Name the event from shape. See the module docstring for why ties go to PreToolUse."""
    if "terminationReason" in raw or "fullyIdle" in raw:
        return "Stop"
    if isinstance(raw.get("toolCall"), dict):
        return "PostToolUse" if "error" in raw else "PreToolUse"
    # PreInvocation / PostInvocation are indistinguishable from each other and unmapped.
    return None


def _content_of(args):
    for key in _CONTENT_ARGS:
        if args.get(key):
            return args[key]
    chunks = args.get("ReplacementChunks")
    if isinstance(chunks, list):
        joined = "\n".join(str(c.get("ReplacementContent", "")) for c in chunks if isinstance(c, dict))
        return joined or None
    return None


def parse(raw):
    name = _infer_event(raw)
    call = raw.get("toolCall") if isinstance(raw.get("toolCall"), dict) else {}
    args = call.get("args") if isinstance(call.get("args"), dict) else {}
    roots = raw.get("workspacePaths") or []
    path = None
    for key in _PATH_ARGS:
        if args.get(key):
            path = args[key]
            break
    return Event(
        AGENT,
        # An event this adapter has no mapping for resolves to UNKNOWN, never to the
        # nearest canonical one: relabelling it invites a guardrail to evaluate the
        # wrong policy against it.
        {"PreToolUse": PRE_TOOL, "PostToolUse": POST_TOOL, "Stop": STOP}.get(name, UNKNOWN),
        tool=call.get("name"),
        command=args.get(_COMMAND_ARG),
        path=path,
        content=_content_of(args),
        output=raw.get("error") or None,
        session_id=raw.get("conversationId"),
        cwd=args.get("Cwd") or (roots[0] if roots else None),
        raw=raw,
    )


def respond(decision, event):
    name = _infer_event(event.raw or {})

    if name == "PostToolUse":
        # Documented as returning an empty object. Nothing here can undo the call.
        return _json.dumps({}), 0

    if name == "Stop":
        # "continue" re-enters the execution loop; any other value lets the stop happen.
        if decision.outcome in (DENY, ASK, REWRITE):
            return _json.dumps({"decision": "continue", "reason": decision.reason or "policy requires more work"}), 0
        return _json.dumps({"decision": "stop"}), 0

    if decision.outcome == REWRITE:
        # No updatedInput equivalent: permissionOverrides widens permissions, it does not
        # change arguments. Allowing the unmodified call through would be the wrong read.
        return _json.dumps(
            {"decision": "deny", "reason": _because(decision.reason, "Antigravity cannot modify a tool call")}
        ), 0
    if decision.outcome == ASK:
        if degraded_from(decision) == REWRITE:
            # A rewrite the dispatcher reduced. Prompting would offer the user the
            # *unmodified* call to approve, which is the thing the handler rejected.
            return _json.dumps(
                {"decision": "deny", "reason": _because(decision.reason, "Antigravity cannot modify a tool call")}
            ), 0
        # A real ask is honoured, but a user's "Always Allow" still applies. force_ask is
        # the variant that ignores cached permissions, and our contract cannot request it.
        return _json.dumps({"decision": "ask", "reason": decision.reason or "confirmation required"}), 0
    if decision.outcome == DENY:
        return _json.dumps({"decision": "deny", "reason": decision.reason or "blocked by policy"}), 0
    return _json.dumps({"decision": "allow"}), 0


def _because(reason, note):
    return "%s (%s)" % (reason, note) if reason else note


#: The group name we own in hooks.json. Antigravity keys the file by hook *name*, which
#: gives ownership a natural home: our entries live under one key nobody else writes.
GROUP = "agentseam"


def hook_config(canonical_events, command, matcher=None):
    group = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        entry = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            entry["matcher"] = matcher
        group.setdefault(name, []).append(entry)
    return {GROUP: group}


CONFIG_PATH = ".agents/hooks.json"
