"""Canonical event vocabulary, normalized envelope, and decision type."""

from __future__ import annotations

import json as _json
import warnings as _warnings

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
        "command",
        "content",
        "cwd",
        "event",
        "output",
        "path",
        "prompt",
        "raw",
        "session_id",
        "tool",
        "tool_use_id",
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
ESCALATE = "escalate"
TRANSFORM = "transform"
WARN = "warn"
VOUCH = "vouch"

# Pre-ACS-alignment names. Same strings as their ACS-named counterparts, so every existing
# `is`/`==` comparison against the old constant keeps working untouched.
ASK = ESCALATE
REWRITE = TRANSFORM

_CANONICAL_OUTCOMES = (ALLOW, DENY, ESCALATE, TRANSFORM, WARN, VOUCH)

# The literal spellings a caller might still pass to Decision(outcome, ...) directly, mapped
# to the value that now backs them. Only needed for the raw-string constructor path --
# Decision.ask()/.rewrite() below build the canonical outcome themselves.
_LEGACY_SPELLING = {"ask": ESCALATE, "rewrite": TRANSFORM}


class Decision:
    """What a handler wants to happen. Adapters translate this to vendor dialect."""

    __slots__ = ("context", "evidence", "outcome", "reason", "updated_input")

    #: Classmethods kept only so existing callers keep constructing; see .ask()/.rewrite().
    DEPRECATED_ALIASES = frozenset({"ask", "rewrite"})

    def __init__(self, outcome, reason=None, updated_input=None, evidence=None, context=None):
        outcome = _LEGACY_SPELLING.get(outcome, outcome)
        if outcome not in _CANONICAL_OUTCOMES:
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
    def escalate(cls, reason, evidence=None, context=None):
        """Defer the action to the host's own approval path (ACS `escalate`)."""
        return cls(ESCALATE, reason, evidence=evidence, context=context)

    @classmethod
    def ask(cls, reason, evidence=None, context=None):
        """Deprecated alias of escalate() -- kept so existing callers keep constructing."""
        _warnings.warn("Decision.ask() is deprecated; use Decision.escalate()", DeprecationWarning, stacklevel=2)
        return cls.escalate(reason, evidence=evidence, context=context)

    @classmethod
    def transform(cls, updated_input, reason=None, evidence=None, context=None):
        """Replace the tool input wholesale (ACS `transform`, at whole-value granularity)."""
        return cls(TRANSFORM, reason, updated_input=updated_input, evidence=evidence, context=context)

    @classmethod
    def rewrite(cls, updated_input, reason=None, evidence=None, context=None):
        """Deprecated alias of transform() -- kept so existing callers keep constructing."""
        _warnings.warn("Decision.rewrite() is deprecated; use Decision.transform()", DeprecationWarning, stacklevel=2)
        return cls.transform(updated_input, reason, evidence=evidence, context=context)

    @classmethod
    def warn(cls, reason=None, evidence=None, context=None):
        """Permit the action with no change, recording a warning (ACS `warn`)."""
        return cls(WARN, reason, evidence=evidence, context=context)

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
