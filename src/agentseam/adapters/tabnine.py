"""Tabnine CLI adapter.

Eleven events, six of which can block -- including `AfterTool`, which is unusual: most
agents treat post-execution as observation only, and Tabnine lets a hook there force a
retry.

Two things shape this adapter, and both narrow what may be promised:

  * **Its event names are Gemini CLI's exactly.** BeforeTool, AfterTool, BeforeAgent,
    AfterAgent, SessionStart, SessionEnd, PreCompress -- every one is shared. The only
    documented separator is `timestamp`, which Tabnine puts in its base schema, so
    `claims()` requires it. That is enough to identify Tabnine but not enough to *exclude*
    Gemini, whose full base schema is not established here, so both adapters claim these
    payloads and `detect()` declines. **Pass `agent="tabnine"` explicitly.** Guessing
    between two adapters that answer differently is worse than saying so.
  * **It fails open in an unusually broad way.** Any exit code other than 0 or 2 is a
    warning and execution proceeds; and stdout that is not valid JSON does not fail the
    hook, it is treated as a `systemMessage` and the action is *allowed*. A crashed or
    chatty hook is therefore a permitted action, which is why the vendor's own warning
    about stray output on stdout is repeated in `respond`.

Rewrite is advertised in the vendor's overview ("Rewrite tool arguments before execution")
but the field carrying it is in a page not read here, so no rewrite is claimed. An
advertised capability with no established mechanism is exactly the kind of claim this
project treats as a bug.

Verified against Tabnine CLI's hooks documentation (2026-08-26).
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
    UNKNOWN,
    Event,
    degraded_from,
)

AGENT = "tabnine"

EVENT_MAP = {
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "BeforeAgent": PROMPT_SUBMIT,
    "AfterAgent": STOP,
    "BeforeTool": PRE_TOOL,
    "AfterTool": POST_TOOL,
    "PreCompress": PRE_COMPACT,
    # BeforeModel, AfterModel, BeforeToolSelection and Notification have no canonical
    # counterpart. Leaving them unmapped keeps the matrix honest rather than inventing
    # coverage; a payload for one resolves to UNKNOWN and is allowed, not guessed at.
}
REVERSE_EVENT_MAP = {
    SESSION_START: "SessionStart",
    SESSION_END: "SessionEnd",
    PROMPT_SUBMIT: "BeforeAgent",
    STOP: "AfterAgent",
    PRE_TOOL: "BeforeTool",
    POST_TOOL: "AfterTool",
    PRE_COMPACT: "PreCompress",
}

#: The events whose decision reaches the agent loop. Six of eleven, which is more than most.
BLOCKING_EVENTS = ("BeforeAgent", "AfterAgent", "BeforeModel", "AfterModel", "BeforeTool", "AfterTool")

#: Canonical form of the four of BLOCKING_EVENTS that have a canonical mapping (BeforeModel/
#: AfterModel do not -- they resolve to UNKNOWN and stay raw-only). respond() is public
#: adapter API: a caller who replays a captured event or builds one directly (raw defaulting
#: to {}) must still get an honest deny, not silence, at a real blocking event.
_BLOCKING_CANONICAL = (PROMPT_SUBMIT, STOP, PRE_TOOL, POST_TOOL)

#: In Tabnine's base schema on every event, and the only documented field separating its
#: payloads from Gemini CLI's identically-named ones.
MARKER = "timestamp"


def claims(raw):
    if not isinstance(raw, dict):
        return False
    return raw.get("hook_event_name") in EVENT_MAP and MARKER in raw


def parse(raw):
    ti = raw.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
    out = raw.get("tool_output") or raw.get("tool_response")
    if isinstance(out, (dict, list)):
        out = _json.dumps(out)
    return Event(
        AGENT,
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
        tool=raw.get("tool_name"),
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("path"),
        content=ti.get("content") or ti.get("new_string"),
        output=out,
        prompt=raw.get("prompt"),
        session_id=raw.get("session_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def _because(reason, note):
    return "%s (%s)" % (reason, note) if reason else note


#: Decision words this vendor accepts -- UNVERIFIED, and the only such entry here. Nothing
#: in this repository records Tabnine's decision values: the docstring above is thorough
#: about events, detection and fail-open and silent on this. These two are what respond()
#: has always emitted, not what the vendor is known to read. If the word is "block" (as it
#: is for Junie and Devin) every deny here is ignored -- and Tabnine treats non-JSON stdout
#: as an allow, so an unrecognised value is a permitted action. Settle it in the live round
#: tabnine already needs; do NOT swap the words on inference.
DECISION_VOCABULARY = frozenset({"allow", "deny"})


def respond(decision, event):
    # event.event first: a caller replaying a captured event or building one directly (raw
    # defaulting to {}) still gets an honest answer at the four blocking events that have a
    # canonical mapping. The raw name catches BeforeModel/AfterModel too, which do not.
    name = (event.raw or {}).get("hook_event_name")
    if event.event not in _BLOCKING_CANONICAL and name not in BLOCKING_EVENTS:
        # Nothing here reaches the agent loop. Emitting JSON anyway would be worse than
        # silence: stdout that is not the final JSON object breaks Tabnine's parsing, and
        # a broken parse is treated as allow.
        return "", 0

    if decision.outcome == DENY or decision.outcome == ASK or decision.outcome == REWRITE:
        reason = decision.reason
        if decision.outcome == ASK:
            note = (
                "Tabnine cannot modify a tool call"
                if degraded_from(decision) == REWRITE
                else "Tabnine cannot prompt for confirmation"
            )
            reason = _because(reason, note)
        elif decision.outcome == REWRITE:
            reason = _because(reason, "Tabnine cannot modify a tool call")
        return _json.dumps({"decision": "deny", "reason": reason or "blocked by policy"}), 0
    return _json.dumps({"decision": "allow"}), 0


def hook_config(canonical_events, command, matcher=None):
    hooks = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        entry = {"hooks": [{"type": "command", "command": command, "name": "agentseam"}]}
        if matcher:
            entry["matcher"] = matcher
        hooks.setdefault(name, []).append(entry)
    return {"hooks": hooks}


CONFIG_PATH = ".tabnine/agent/settings.json"
