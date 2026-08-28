"""Gemini CLI adapter.

Verified against the vendor's own hooks reference (docs/hooks/reference.md in
google-gemini/gemini-cli). Notable differences from the Claude-family contract:

  * events are Before*/After*, not Pre*/Post*
  * the decision field is `decision: "allow" | "deny"` at the TOP level, with
    `reason` — not nested under hookSpecificOutput
  * a rewrite is `hookSpecificOutput.tool_input`, which MERGES WITH and overrides
    the model's arguments rather than replacing them wholesale
  * exit code 2 also blocks, using stderr as the reason
  * write tools are named write_file / replace, not Write / Edit
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
    UNKNOWN,
    Event,
)
from .claude_code import looks_like_claude_code

AGENT = "gemini_cli"

EVENT_MAP = {
    "BeforeTool": PRE_TOOL,
    "AfterTool": POST_TOOL,
    "BeforeAgent": PROMPT_SUBMIT,
    "AfterAgent": STOP,
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "PreCompress": PRE_COMPACT,
}
REVERSE_EVENT_MAP = {
    PRE_TOOL: "BeforeTool",
    POST_TOOL: "AfterTool",
    PROMPT_SUBMIT: "BeforeAgent",
    STOP: "AfterAgent",
    SESSION_START: "SessionStart",
    SESSION_END: "SessionEnd",
    PRE_COMPACT: "PreCompress",
}

# Gemini's file-writing tools. `replace` is an edit; `write_file` is a whole-file write.
WRITE_TOOLS = ("write_file", "replace")
# Its shell tool carries the command under a different key than the Claude family.
SHELL_TOOLS = ("run_shell_command",)


#: Agents that name themselves in the payload. A payload naming a different client is not
#: ours, whatever its event is called -- SessionStart and SessionEnd are spelled the same
#: way by Claude Code, Devin and Kimi Code, and only Kimi carries proof of which it is.
#: Claude Code's adapter applies the same rule; the general form is that a positive
#: self-identification beats a shared event name.
_OWN_CLIENT_TYPES = (None, "gemini_cli", "gemini")

#: Positive nameplates other vendors sharing this envelope actually send. Gemini's own
#: payload is a strict SUBSET of theirs -- it has no field of its own to claim on -- so
#: claiming whenever no foreign `client_type` is present made this adapter swallow every
#: unlabelled payload in the corpus: 13 of the 15 shipping payloads that resolve to the
#: wrong adapter, including all four of Tabnine's gating events, whose deny then vanished
#: entirely under auto-detection. Absence of somebody else's nameplate is not evidence
#: about us. Defer to any adapter holding positive proof.
_FOREIGN_MARKERS = (
    "timestamp",  # tabnine.MARKER
    "project_path",  # junie.MARKER
    "prompt_id",  # devin
    "turn_id",  # codex_cli
)


def claims(raw):
    if not isinstance(raw, dict) or raw.get("hook_event_name") not in EVENT_MAP:
        return False
    if raw.get("client_type") not in _OWN_CLIENT_TYPES:
        return False
    if any(marker in raw for marker in _FOREIGN_MARKERS) or looks_like_claude_code(raw):
        return False
    return True


def parse(raw):
    ti = raw.get("tool_input")
    # A guard that crashes is a guard that allows: dispatch only wraps the JSON decode, so
    # an exception here kills the hook with exit 1, which most vendors treat as a
    # non-blocking error and let the call through. tool_input is whatever the agent chose
    # to serialise, so it is not ours to assume the shape of.
    ti = ti if isinstance(ti, dict) else {}
    tool = raw.get("tool_name")
    content = None
    if tool in WRITE_TOOLS:
        # write_file uses `content`; replace supplies the replacement text.
        content = ti.get("content") or ti.get("new_string") or ti.get("new_str")
    return Event(
        AGENT,
        # An event this adapter has no mapping for resolves to UNKNOWN, never to the
        # nearest canonical one: relabelling it invites a guardrail to evaluate the
        # wrong policy against it.
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
        tool=tool,
        command=ti.get("command"),
        path=ti.get("file_path") or ti.get("absolute_path") or ti.get("path"),
        content=content,
        output=raw.get("tool_output") or raw.get("tool_response"),
        prompt=raw.get("prompt") or raw.get("user_message"),
        session_id=raw.get("session_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


#: Decision words this vendor accepts: a top-level `decision` of allow, deny or ask. No
#: "block" -- `isBlockingDecision()` tests block|deny, so "block" is read, but "deny" is the
#: word the reference documents and the only one this adapter emits.
#:
#: "ask" was absent here until 2026-08-28 on the strength of the docs alone. Source says
#: otherwise -- see respond().
DECISION_VOCABULARY = frozenset({"allow", "deny", "ask"})

#: The one event that reads an `ask`. See respond().
_ASK_EVENT = "BeforeTool"


#: The events whose stdout decision is actually read. session_start, session_end and
#: pre_compact are observation-only in this row, and respond() emitted a full
#: {"decision": "deny"} at all three until 2026-08-28 -- a verdict nobody reads, which
#: invites a log or a consumer to record a block that never happened. Gemini has no
#: additionalContext channel recorded here, so the honest answer there is silence.
_BLOCKING_EVENTS = ("BeforeTool", "AfterTool", "BeforeAgent", "AfterAgent")


def respond(decision, event):
    import json as _json

    name = (event.raw or {}).get("hook_event_name")
    if name not in _BLOCKING_EVENTS:
        return "", 0

    if decision.outcome == DENY:
        # `reason` is required on a deny and is delivered TO THE AGENT as a tool
        # error, so it should read as an instruction the model can act on.
        return _json.dumps({"decision": "deny", "reason": decision.reason or "blocked by policy"}), 0
    if decision.outcome == ASK:
        if name == _ASK_EVENT:
            # An ask IS honoured here, and this adapter denied instead until 2026-08-28 --
            # a guardrail that meant "let the human choose" was answered with "blocked",
            # and the human never saw the choice. The docs do not say so; the source does:
            # hook-utils.ts routes isAskDecision() to hookDecision='ask', scheduler.ts
            # turns that into PolicyDecision.ASK_USER and calls resolveConfirmation with
            # forcedDecision:'ask_user'. Forced is the operative word -- it prompts even
            # where the user's own policy rule would have auto-allowed the call, which is
            # a stronger ask than most vendors here can express.
            return _json.dumps({"decision": "ask", "reason": decision.reason or "confirmation required"}), 0
        # Everywhere else an ask is inert: BeforeAgent and AfterAgent consult only
        # isBlockingDecision(), so "ask" there is a word nothing reads, and a verdict
        # nobody reads is a pass. Denying with the explanation is the honest translation.
        return (
            _json.dumps(
                {
                    "decision": "deny",
                    "reason": "%s (confirmation required; %s cannot prompt from a hook)"
                    % (decision.reason or "policy requires confirmation", name),
                }
            ),
            0,
        )
    if decision.outcome == REWRITE:
        return _json.dumps({"hookSpecificOutput": {"tool_input": decision.updated_input}}), 0
    # An explicit allow, and it costs nothing: Gemini never READS this word. Only
    # isBlockingDecision() (block|deny) and isAskDecision() (ask) are consulted anywhere in
    # the tree, and hookAggregator synthesises decision:'allow' itself when no hook blocked
    # or asked. So the word is inert -- identical in effect to silence, and unable to skip
    # a confirmation the way VS Code's permissionDecision:"allow" does. It stays because
    # it is what the vendor's own reference documents a hook returning.
    return _json.dumps({"decision": "allow"}), 0


def hook_config(canonical_events, command, matcher=None):
    hooks = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        entry = {"hooks": [{"type": "command", "command": command}]}
        if matcher:
            entry["matcher"] = matcher
        hooks.setdefault(name, []).append(entry)
    return {"hooks": hooks}


CONFIG_PATH = ".gemini/settings.json"
