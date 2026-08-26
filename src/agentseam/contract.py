"""Canonical event vocabulary, normalized envelope, and decision type.

This is L0: the contract every adapter speaks. Nothing here knows any vendor.
Stdlib only — this module is embedded verbatim into rendered single-file adapters.
"""

from __future__ import annotations

# --- canonical lifecycle events -------------------------------------------------
# Vendor event names map ONTO these; adapters own the mapping. A vendor that lacks
# an event simply has no row for it in the capability matrix — that absence is the
# honest coverage floor, not something to paper over.
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

# --- normalized envelope --------------------------------------------------------


class Event:
    """One agent lifecycle event, normalized.

    `raw` is always kept: adapters normalize the fields consumers usually want, and
    a consumer that needs something vendor-specific can still reach it rather than
    being blocked by our vocabulary.
    """

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
        self.command = command  # shell command, when the tool carries one
        self.path = path  # target file, when the tool writes one
        self.content = content  # file text being written (pre_tool on write tools)
        self.output = output  # tool result (post_tool)
        self.prompt = prompt  # user prompt text (prompt_submit)
        self.session_id = session_id
        self.tool_use_id = tool_use_id
        self.cwd = cwd
        self.raw = raw if raw is not None else {}

    def __repr__(self):  # pragma: no cover - debugging aid
        return "Event(%s/%s tool=%r path=%r)" % (self.agent, self.event, self.tool, self.path)


# --- decisions ------------------------------------------------------------------

ALLOW = "allow"
DENY = "deny"
ASK = "ask"
REWRITE = "rewrite"


class Decision:
    """What a handler wants to happen. Adapters translate this to vendor dialect.

    `evidence` is an optional payload-free dict a consumer can carry through to its
    own log; agentseam never writes it anywhere itself.
    """

    __slots__ = ("outcome", "reason", "updated_input", "evidence")

    def __init__(self, outcome, reason=None, updated_input=None, evidence=None):
        if outcome not in (ALLOW, DENY, ASK, REWRITE):
            raise ValueError("unknown outcome: %r" % (outcome,))
        self.outcome = outcome
        self.reason = reason
        self.updated_input = updated_input
        self.evidence = evidence or {}

    # constructors read better at call sites than Decision("deny", ...)
    @classmethod
    def allow(cls, reason=None, evidence=None):
        return cls(ALLOW, reason, evidence=evidence)

    @classmethod
    def deny(cls, reason, evidence=None):
        return cls(DENY, reason, evidence=evidence)

    @classmethod
    def ask(cls, reason, evidence=None):
        return cls(ASK, reason, evidence=evidence)

    @classmethod
    def rewrite(cls, updated_input, reason=None, evidence=None):
        return cls(REWRITE, reason, updated_input=updated_input, evidence=evidence)

    def __repr__(self):  # pragma: no cover - debugging aid
        return "Decision(%s, %r)" % (self.outcome, self.reason)


def degraded_from(decision):
    """What this decision was before the dispatcher reduced it, or None.

    An adapter explaining why an outcome changed shape has to read this, not the outcome
    it was handed. A rewrite reduced to `ask` and then blocked by an agent that cannot
    prompt would otherwise be reported as a confirmation request that failed -- and it was
    never a confirmation request.
    """
    return (decision.evidence or {}).get("degraded_from")
