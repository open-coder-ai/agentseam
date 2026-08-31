"""Antigravity adapter."""

from __future__ import annotations

import json as _json

from ..contract import ASK, DENY, POST_TOOL, PRE_TOOL, REWRITE, STOP, UNKNOWN, Event, degraded_from

AGENT = "antigravity"

REVERSE_EVENT_MAP = {PRE_TOOL: "PreToolUse", POST_TOOL: "PostToolUse", STOP: "Stop"}

_COMMAND_ARG = "CommandLine"
_PATH_ARGS = ("TargetFile", "AbsolutePath")
_CONTENT_ARGS = ("CodeContent", "ReplacementContent")


def claims(raw):
    """Structural: `conversationId` with `workspacePaths` is Antigravity's own envelope."""
    if not isinstance(raw, dict):
        return False
    return "conversationId" in raw and isinstance(raw.get("workspacePaths"), list)


def _infer_event(raw):
    """Name the event from shape. See the module docstring for why ties go to PreToolUse."""
    if "terminationReason" in raw or "fullyIdle" in raw:
        return "Stop"
    if isinstance(raw.get("toolCall"), dict):
        return "PostToolUse" if "error" in raw else "PreToolUse"
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
        {"PreToolUse": PRE_TOOL, "PostToolUse": POST_TOOL, "Stop": STOP}.get(name, UNKNOWN),
        tool=call.get("name"),
        command=args.get(_COMMAND_ARG),
        path=path,
        content=_content_of(args),
        output=raw.get("error") or None,
        session_id=raw.get("conversationId"),
        tool_use_id=str(raw["stepIdx"]) if "stepIdx" in raw else None,
        cwd=args.get("Cwd") or (roots[0] if roots else None),
        raw=raw,
    )


DECISION_VOCABULARY = frozenset({"allow", "deny", "ask", "force_ask", "deny_unless_prior_grant", "continue", "stop"})


def respond(decision, event):
    name = _infer_event(event.raw or {})

    if name == "PostToolUse":
        return _json.dumps({}), 0

    if name == "Stop":
        if decision.outcome == ASK:
            note = (
                "Antigravity cannot modify a tool call"
                if degraded_from(decision) == REWRITE
                else "Antigravity cannot prompt at Stop"
            )
            reason = _because(decision.reason, note)
            return _json.dumps({"decision": "continue", "reason": reason}), 0
        if decision.outcome == REWRITE:
            reason = _because(decision.reason, "Antigravity cannot modify a tool call")
            return _json.dumps({"decision": "continue", "reason": reason}), 0
        if decision.outcome == DENY:
            return _json.dumps({"decision": "continue", "reason": decision.reason or "policy requires more work"}), 0
        return _json.dumps({"decision": "stop"}), 0

    if decision.outcome == REWRITE:
        return _json.dumps(
            {"decision": "deny", "reason": _because(decision.reason, "Antigravity cannot modify a tool call")}
        ), 0
    if decision.outcome == ASK:
        if degraded_from(decision) == REWRITE:
            return _json.dumps(
                {"decision": "deny", "reason": _because(decision.reason, "Antigravity cannot modify a tool call")}
            ), 0
        return _json.dumps({"decision": "ask", "reason": decision.reason or "confirmation required"}), 0
    if decision.outcome == DENY:
        return _json.dumps({"decision": "deny", "reason": decision.reason or "blocked by policy"}), 0
    return _json.dumps({"decision": "allow"}), 0


def _because(reason, note):
    return "%s (%s)" % (reason, note) if reason else note


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
