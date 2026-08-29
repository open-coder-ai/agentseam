"""Canonical event vocabulary, normalized envelope, and decision type.

This is L0: the contract every adapter speaks. Nothing here knows any vendor.
Stdlib only — this module is embedded verbatim into rendered single-file adapters.
"""

from __future__ import annotations

import json as _json

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

#: Not a lifecycle event: the honest answer when a vendor sends something this adapter has
#: no mapping for. Deliberately outside EVENTS, so a handler matching on the vocabulary can
#: never match it by accident.
#:
#: The alternative was what several adapters used to do -- fall back to the nearest
#: canonical event -- which reports an unknown event as `pre_tool` and invites a guardrail
#: to evaluate a pre-tool policy against something that is not one. New vendor events appear
#: without warning; being told is the only safe outcome.
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
#: "I actively approve -- skip the user's own confirmation," never the default. ALLOW means
#: no objection; a bare ALLOW that spoke this loudly was the exact defect
#: allow_semantics.py exists to audit. VOUCH is that same loud word, used on purpose, on the
#: vendors it is established to mean this. See dispatch.degrade() and
#: allow_semantics.VOUCH_SPEAKS for which those are, and how everyone else degrades.
VOUCH = "vouch"


class Decision:
    """What a handler wants to happen. Adapters translate this to vendor dialect.

    `evidence` is an optional payload-free dict a consumer can carry through to its
    own log; agentseam never writes it anywhere itself.

    `context` is different: free text meant to reach the MODEL, on the few vendor
    surfaces that take side-channel context injection independent of the outcome
    (Claude Code's hookSpecificOutput.additionalContext at SessionStart and
    UserPromptSubmit today). An adapter with no such surface drops it silently --
    the same honest-degrade shape as an unsupported outcome, not a promise every
    vendor can keep. It is advisory content, never a substitute for `reason`, which
    still speaks to the vendor's own decision/refusal dialect.
    """

    __slots__ = ("outcome", "reason", "updated_input", "evidence", "context")

    def __init__(self, outcome, reason=None, updated_input=None, evidence=None, context=None):
        if outcome not in (ALLOW, DENY, ASK, REWRITE, VOUCH):
            raise ValueError("unknown outcome: %r" % (outcome,))
        self.outcome = outcome
        self.reason = reason
        self.updated_input = updated_input
        self.evidence = evidence or {}
        self.context = context

    # constructors read better at call sites than Decision("deny", ...)
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
    """What this decision was before the dispatcher reduced it, or None.

    An adapter explaining why an outcome changed shape has to read this, not the outcome
    it was handed. A rewrite reduced to `ask` and then blocked by an agent that cannot
    prompt would otherwise be reported as a confirmation request that failed -- and it was
    never a confirmation request.
    """
    return (decision.evidence or {}).get("degraded_from")


def tool_input_of(raw):
    """The tool's arguments as a dict, decoding the JSON-string form some vendors send.

    `tool_input` is whatever the agent chose to serialise, and it is not always an object.
    Witnessed live on VS Code Copilot (2026-08-29), same adapter and same `Edit` tool, in
    two runs routed to different models: once as an object with path/old_str/new_str, once
    as a 129-character JSON *string*. Both are the vendor's real wire format.

    That difference is not cosmetic. Against the object the parser reports the file and the
    content; against the string it reported neither, so a policy denying on secret content
    saw an empty write and allowed it. The adapters guarded the string case against a crash
    (a crash is an allow) but resolved it to `{}`, which is a quieter version of the same
    outcome: the guard is blind and says nothing about it.

    Decoding is not a guess about an unrecorded shape -- a string that parses to a JSON
    object IS that object, and the alternative is discarding data the vendor sent. Only a
    dict counts: a JSON list or scalar is not a set of tool arguments, and `{}` remains the
    honest answer for anything that does not parse.
    """
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
