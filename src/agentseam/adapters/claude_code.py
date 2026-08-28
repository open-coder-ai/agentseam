"""Claude Code adapter.

Payload: {"tool_name", "tool_input", "session_id", "tool_use_id", "hook_event_name", ...}
Response: {"hookSpecificOutput": {"hookEventName", "permissionDecision", ...}} on stdout;
exit 2 also blocks. Verified live against Claude Code 2.1.245 (2026-08-25).
"""

from __future__ import annotations

from ..contract import (
    ALLOW,
    ASK,
    DENY,
    FILE_CHANGED,
    INSTRUCTIONS_LOADED,
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
)

AGENT = "claude_code"

# vendor event name -> canonical
EVENT_MAP = {
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "PostToolUseFailure": TOOL_FAILURE,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "SessionStart": SESSION_START,
    "SessionEnd": SESSION_END,
    "Stop": STOP,
    "PreCompact": PRE_COMPACT,
    "SubagentStart": SUBAGENT_START,
    "SubagentStop": SUBAGENT_STOP,
    # Both were claimed by the matrix long before they were mapped here, so an install for
    # them wired nothing at all and said nothing about it. FileChanged fires when a watched
    # file changes on disk (the matcher names the files); InstructionsLoaded fires when a
    # CLAUDE.md or .claude/rules/*.md is read into context, at session start and again
    # whenever one is loaded lazily.
    "InstructionsLoaded": INSTRUCTIONS_LOADED,
    "FileChanged": FILE_CHANGED,
}
REVERSE_EVENT_MAP = {v: k for k, v in EVENT_MAP.items()}

# Tools whose input carries file content rather than a shell command.
WRITE_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


#: Fields observed in real Claude Code payloads (live capture, v3.17.8 era, 2026-08-27) that
#: no other adapter's documented envelope lists. Positive evidence, not inferred absence --
#: which is the distinction that broke detection here. `prompt_id` was once treated as proof
#: a payload was NOT Claude Code's; Claude Code now sends it on nearly every event, so that
#: negative test rejected 38 of 42 real payloads and handed them to Devin instead.
OBSERVED_MARKERS = (
    "transcript_path",
    "permission_mode",
    "stop_hook_active",
    "agent_transcript_path",
    "background_tasks",
    "session_crons",
    "custom_instructions",
    "effort",
)


def looks_like_claude_code(raw):
    """True when the payload carries a field only Claude Code has been seen to send.

    Imported by the adapters that share this envelope, so the discriminator lives in one
    place and cannot drift into two disagreeing copies.
    """
    return isinstance(raw, dict) and any(marker in raw for marker in OBSERVED_MARKERS)


def claims(raw):
    """True when this payload looks like Claude Code's shape."""
    if not isinstance(raw, dict):
        return False
    if raw.get("hook_event_name") in EVENT_MAP:
        # Codex reuses tool_input but adds turn identifiers, and Devin reuses the whole
        # event vocabulary but adds a per-turn prompt_id. Claiming either would make
        # detect() ambiguous, and an unidentified payload is allowed through.
        # Kimi Code CLI is Claude Code's envelope exactly -- same PascalCase events, same
        # snake_case fields -- and names itself only in client_type.
        if raw.get("client_type") not in (None, "claude_code"):
            return False
        # Junie reuses this whole event vocabulary on purpose -- it says so -- and sends
        # project_path, which Claude Code does not. Without this the two are one payload.
        # Foreign nameplates: Codex's turn_id, Junie's project_path, Tabnine's timestamp.
        # None appears in any real Claude Code payload observed live, and each is the only
        # documented thing separating that vendor's identically-named events from ours.
        if "turn_id" in raw or "project_path" in raw or "timestamp" in raw:
            return False
        # `prompt_id` used to be treated as proof this was Devin's payload, not ours. Claude
        # Code now sends it too, so the field alone settles nothing: it is only Devin's when
        # nothing we have actually observed from Claude Code is alongside it.
        if "prompt_id" in raw and not looks_like_claude_code(raw):
            return False
        return True
    return False


def parse(raw):
    ti = raw.get("tool_input") or {}
    tool = raw.get("tool_name")
    # new_source is NotebookEdit's cell body -- the tool is in WRITE_TOOLS, so claiming to
    # handle it while dropping its content is an internal contradiction, not a vendor guess.
    content = ti.get("content") or ti.get("new_string") or ti.get("new_source") or None
    if content is None and isinstance(ti.get("edits"), list):
        joined = "\n".join(str(e.get("new_string", "")) for e in ti["edits"])
        content = joined or None
    out = raw.get("tool_output")
    if isinstance(out, (dict, list)):
        import json as _json

        out = _json.dumps(out)
    return Event(
        AGENT,
        # An event this adapter has no mapping for resolves to UNKNOWN, never to the
        # nearest canonical one: relabelling it invites a guardrail to evaluate the
        # wrong policy against it.
        EVENT_MAP.get(raw.get("hook_event_name"), UNKNOWN),
        tool=tool,
        command=ti.get("command"),
        # InstructionsLoaded and FileChanged carry no tool_input at all -- file_path (and,
        # for InstructionsLoaded, content) sit at the top level instead, per the project's
        # own recorded example payloads (examples/generated/claude_code.md).
        path=ti.get("file_path") or ti.get("path") or ti.get("notebook_path") or raw.get("file_path"),
        content=content or raw.get("content"),
        output=out,
        prompt=raw.get("prompt"),
        session_id=raw.get("session_id"),
        tool_use_id=raw.get("tool_use_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


#: Events that read a TOP-LEVEL {"decision": "block", "reason": ...} and ignore
#: hookSpecificOutput.permissionDecision entirely. Established by live experiment against
#: Claude Code 2.1.247 (2026-08-28), not from documentation -- two reads of the vendor page
#: gave contradictory answers, and the shape this adapter had been emitting turned out to be
#: read by neither. See respond() for the result table.
_BLOCK_DIALECT_EVENTS = (PROMPT_SUBMIT, STOP)


def _refusal_reason(decision):
    """One reason string for the events that can only block -- no ask, no rewrite.

    Both degrade to a block with the degradation named rather than being dropped: silence
    at a blocking event is the dispatcher's allow, which is not what the caller asked for.
    """
    reason = decision.reason or "blocked by policy"
    if decision.outcome == ASK:
        return reason + " (confirmation requested; this event cannot prompt, so it blocks)"
    if decision.outcome == REWRITE:
        return reason + " (input rewrite requested; this event cannot modify input, so it blocks)"
    return reason


def respond(decision, event):
    """(stdout_text, exit_code) for this decision -- three dialects, not one.

    Until 2026-08-28 this emitted hookSpecificOutput.permissionDecision at EVERY event.
    A live experiment against Claude Code 2.1.247 settled what each event actually reads,
    by wiring one candidate shape per trial and watching the agent rather than the hook:

        event             {"decision": "block"}   hookSpecificOutput   exit 2
        UserPromptSubmit  honoured                IGNORED              honoured
        Stop              honoured                IGNORED              honoured

    So every prompt_submit and stop deny this library has ever produced on its most-used
    adapter was silently discarded: the handler refused, the dispatcher reported a block,
    and the prompt reached the model anyway. At prompt_submit the trial prompt asked the
    agent to write a marker file and the file appeared; at stop the agent carried on and
    the Stop hook re-fired with stop_hook_active set. Both signals are things the agent
    did, not things the probe claimed.

    exit 2 works at both, and is deliberately NOT used: it collapses to 1 under the
    PowerShell wrapper some vendors apply (which is what made the exit-code path useless on
    Codex/Windows), and it leaks the full hook command line into the UI where the JSON form
    does not. The JSON block also carries the reason into the model's context.

    pre_tool keeps hookSpecificOutput.permissionDecision, which is its established contract
    and was not part of this experiment. Everything else is observation-only in this row and
    gets silence -- a verdict there was never read.
    """
    import json as _json

    if event.event in _BLOCK_DIALECT_EVENTS:
        if decision.outcome == ALLOW:
            return "", 0
        return _json.dumps({"decision": "block", "reason": _refusal_reason(decision)}), 0

    if event.event != PRE_TOOL:
        return "", 0

    out = {"hookEventName": REVERSE_EVENT_MAP.get(event.event, "PreToolUse")}
    if decision.outcome == DENY:
        out["permissionDecision"] = "deny"
        out["permissionDecisionReason"] = decision.reason or "blocked"
    elif decision.outcome == ASK:
        out["permissionDecision"] = "ask"
        out["permissionDecisionReason"] = decision.reason or "confirmation required"
    elif decision.outcome == REWRITE:
        out["permissionDecision"] = "allow"
        out["updatedInput"] = decision.updated_input
        if decision.reason:
            out["permissionDecisionReason"] = decision.reason
    else:
        out["permissionDecision"] = "allow"
    return _json.dumps({"hookSpecificOutput": out}), 0


def hook_config(canonical_events, command, matcher=None):
    """A settings.json `hooks` fragment wiring `command` for these canonical events."""
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


CONFIG_PATH = ".claude/settings.json"
