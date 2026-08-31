"""Canonical event vocabulary, normalized envelope, and decision type."""

from __future__ import annotations

import json as _json

SESSION_START = "session_start"
SESSION_END = "session_end"
PROMPT_SUBMIT = "prompt_submit"
PRE_TOOL = "pre_tool"
POST_TOOL = "post_tool"
TOOL_FAILURE = "tool_failure"
PRE_COMPACT = "pre_compact"
STOP = "stop"
SUBAGENT_START = "subagent_start"
SUBAGENT_STOP = "subagent_stop"
INSTRUCTIONS_LOADED = "instructions_loaded"
FILE_CHANGED = "file_changed"

UNKNOWN = "unknown"

EVENTS = (
    SESSION_START,
    SESSION_END,
    PROMPT_SUBMIT,
    PRE_TOOL,
    POST_TOOL,
    TOOL_FAILURE,
    PRE_COMPACT,
    STOP,
    SUBAGENT_START,
    SUBAGENT_STOP,
    INSTRUCTIONS_LOADED,
    FILE_CHANGED,
)


class Event:
    """One agent lifecycle event, normalized."""

    __slots__ = (
        "agent",
        "event",
        "tool",
        "command",
        "path",
        "content",
        "output",
        "prompt",
        "session_id",
        "tool_use_id",
        "cwd",
        "raw",
    )

    def __init__(
        self,
        agent,
        event,
        *,
        tool=None,
        command=None,
        path=None,
        content=None,
        output=None,
        prompt=None,
        session_id=None,
        tool_use_id=None,
        cwd=None,
        raw=None,
    ):
        self.agent = agent
        self.event = event
        self.tool = tool
        self.command = command
        self.path = path
        self.content = content
        self.output = output
        self.prompt = prompt
        self.session_id = session_id
        self.tool_use_id = tool_use_id
        self.cwd = cwd
        self.raw = raw if raw is not None else {}

    def __repr__(self):  # pragma: no cover - debugging aid
        return "Event(%s/%s tool=%r path=%r)" % (self.agent, self.event, self.tool, self.path)


ALLOW = "allow"
DENY = "deny"
ASK = "ask"
REWRITE = "rewrite"
VOUCH = "vouch"


class Decision:
    """What a handler wants to happen. Adapters translate this to vendor dialect."""

    __slots__ = ("outcome", "reason", "updated_input", "evidence", "context")

    def __init__(self, outcome, reason=None, updated_input=None, evidence=None, context=None):
        if outcome not in (ALLOW, DENY, ASK, REWRITE, VOUCH):
            raise ValueError("unknown outcome: %r" % (outcome,))
        self.outcome = outcome
        self.reason = reason
        self.updated_input = updated_input
        self.evidence = evidence or {}
        self.context = context

    @classmethod
    def allow(cls, reason=None, evidence=None, context=None):
        return cls(ALLOW, reason, evidence=evidence, context=context)

    @classmethod
    def deny(cls, reason, evidence=None, context=None):
        return cls(DENY, reason, evidence=evidence, context=context)

    @classmethod
    def ask(cls, reason, evidence=None, context=None):
        return cls(ASK, reason, evidence=evidence, context=context)

    @classmethod
    def rewrite(cls, updated_input, reason=None, evidence=None, context=None):
        return cls(REWRITE, reason, updated_input=updated_input, evidence=evidence, context=context)

    @classmethod
    def vouch(cls, reason=None, evidence=None, context=None):
        return cls(VOUCH, reason, evidence=evidence, context=context)

    def __repr__(self):  # pragma: no cover - debugging aid
        return "Decision(%s, %r)" % (self.outcome, self.reason)


def degraded_from(decision):
    """What this decision was before the dispatcher reduced it, or None."""
    return (decision.evidence or {}).get("degraded_from")


def tool_input_of(raw):
    """The tool's arguments as a dict, decoding the JSON-string form some vendors send."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw[:1] == "{":
        try:
            parsed = _json.loads(raw)
        except Exception:
            return {}
        if isinstance(parsed, dict):
            return parsed
    return {}
