"""Cursor adapter.

Cursor exposes three separate hook surfaces, and keeping them apart is the point:

  * **Agent hooks** fire during Cmd+K / Agent Chat. `preToolUse` is generic -- it fires for
    *every* tool (Shell, Read, Write, MCP, Task) -- and its response carries `updated_input`,
    so this is a genuine block-and-rewrite gate, including on file writes.
  * **Tab hooks** fire for inline completions only, so a policy can treat autonomous Tab
    edits differently from user-directed agent work.
  * **App lifecycle** (`workspaceOpen`) fires outside any session and has no canonical event
    here; it is left unmapped rather than bent into one that means something else.

Three vendor facts shape the response code, and each one costs something if ignored:

  * `ask` is accepted by the `preToolUse` schema **but not enforced today**. Returning it
    there would read as a prompt and behave as a pass, so we deny instead and say why.
    On `beforeShellExecution` / `beforeMCPExecution` an `ask` is honoured.
  * `afterFileEdit` supports **no output fields at all**, and the write has already landed.
    A deny there can only be recorded.
  * Hooks fail **open** by default; `failClosed: true` per hook definition makes them fail
    closed. So Cursor's enforcement level is a configuration choice, not a fixed property --
    `hook_config()` sets it on the gates where failing open would be the wrong answer.

Verified against Cursor's own hooks documentation (2026-08-26).
"""

from __future__ import annotations

import json as _json

from ..contract import (
    ASK,
    DENY,
    FILE_CHANGED,
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
    degraded_from,
)

AGENT = "cursor"

EVENT_MAP = {
    # agent surface
    "sessionStart": SESSION_START,
    "sessionEnd": SESSION_END,
    "preToolUse": PRE_TOOL,
    "postToolUse": POST_TOOL,
    "postToolUseFailure": TOOL_FAILURE,
    "subagentStart": SUBAGENT_START,
    "subagentStop": SUBAGENT_STOP,
    "beforeShellExecution": PRE_TOOL,
    "afterShellExecution": POST_TOOL,
    "beforeMCPExecution": PRE_TOOL,
    "afterMCPExecution": POST_TOOL,
    "beforeReadFile": PRE_TOOL,
    "afterFileEdit": FILE_CHANGED,
    "beforeSubmitPrompt": PROMPT_SUBMIT,
    "preCompact": PRE_COMPACT,
    "stop": STOP,
    # tab surface -- same canonical events, distinguishable by `event.tool`
    "beforeTabFileRead": PRE_TOOL,
    "afterTabFileEdit": FILE_CHANGED,
}

#: Gates whose response is `{"permission": ...}`. The value says whether `ask` is honoured.
_PERMISSION_GATES = {
    "preToolUse": False,  # schema accepts "ask"; Cursor does not enforce it today
    "beforeShellExecution": True,
    "beforeMCPExecution": True,
    "beforeReadFile": False,  # allow/deny only
    "beforeTabFileRead": False,
}

#: Every event where a decision is expected -- NOT the set above, which answers which
#: dialect a gate speaks. Reusing that one here left beforeSubmitPrompt, a gate speaking
#: `continue` rather than `permission`, installed fail-OPEN -- Cursor's default.
_GATES = frozenset(_PERMISSION_GATES) | {"beforeSubmitPrompt"}

#: Post-hoc events: the action already happened, so nothing we return can prevent it.
#: postToolUseFailure is its sibling postToolUse's failure twin -- same TOOL_FAILURE/
#: POST_TOOL shape, same "already happened" fact -- and was missing here, so a deny/ask at
#: a failed tool call returned silence instead of the additional_context detection record
#: every other post-hoc event gets.
_POST_HOC = (
    "postToolUse",
    "postToolUseFailure",
    "afterShellExecution",
    "afterMCPExecution",
    "afterFileEdit",
    "afterTabFileEdit",
)

#: Events with no output contract at all -- returning JSON here is simply ignored.
_MUTE = ("afterFileEdit", "afterTabFileEdit")


#: Fields Cursor's base schema puts on every hook event. Used as positive identification
#: where the event name alone is not enough.
_CURSOR_MARKERS = ("conversation_id", "generation_id", "cursor_version", "workspace_roots")

#: Event names Cursor shares with OpenAI Codex CLI, which also spells its events in
#: camelCase. On these the name proves nothing, so a Cursor marker has to be present --
#: otherwise both adapters claim the payload, detection goes ambiguous, and the dispatcher
#: allows the call it was installed to gate.
_AMBIGUOUS_NAMES = (
    "preToolUse",
    "postToolUse",
    "sessionStart",
    "sessionEnd",
    "preCompact",
    "stop",
    "subagentStart",
    "subagentStop",
)


def claims(raw):
    """True when this payload looks like Cursor's shape."""
    if not isinstance(raw, dict):
        return False
    name = raw.get("hook_event_name")
    if name in EVENT_MAP:
        if name in _AMBIGUOUS_NAMES:
            return any(k in raw for k in _CURSOR_MARKERS)
        return True
    # Cursor does not always name the event. These shapes are unambiguous:
    # beforeShellExecution puts `command` at the top level beside cwd/sandbox.
    if isinstance(raw.get("command"), str) and ("sandbox" in raw or "cwd" in raw) and "tool_input" not in raw:
        return True
    # afterFileEdit: file_path + edits[], with no tool_name wrapper.
    return "file_path" in raw and isinstance(raw.get("edits"), list) and "tool_name" not in raw


def _content_of(raw):
    edits = raw.get("edits")
    if isinstance(edits, list):
        return "\n".join(str(e.get("new_string", "")) for e in edits) or None
    ti = raw.get("tool_input")
    if isinstance(ti, dict):
        return ti.get("content") or ti.get("new_string") or None
    # The read gates put the file's text at the TOP level -- the asymmetry `path` handles
    # below. Last in the chain, so nothing carrying content elsewhere moves.
    content = raw.get("content")
    return content if isinstance(content, str) and content else None


def parse(raw):
    name = raw.get("hook_event_name")
    if name is None:
        # Cursor does not always name the event, so shape decides -- but only when there is
        # no name. A name we do not recognise is a new event, and guessing at one is how an
        # unknown event gets reported as the gate.
        name = "afterFileEdit" if isinstance(raw.get("edits"), list) else "beforeShellExecution"
    ti = raw.get("tool_input")
    ti = ti if isinstance(ti, dict) else {}
    command = raw.get("command") or ti.get("command")
    # preToolUse nests the target inside tool_input; the file-scoped hooks put it at the
    # top level. Reading only one of the two leaves a guardrail asking "which file?" with
    # no answer on exactly the gate that could still stop the write.
    path = raw.get("file_path") or ti.get("file_path") or ti.get("path")
    return Event(
        AGENT,
        # An event this adapter has no mapping for resolves to UNKNOWN, never to the
        # nearest canonical one: relabelling it invites a guardrail to evaluate the
        # wrong policy against it.
        EVENT_MAP.get(name, UNKNOWN),
        tool=raw.get("tool_name") or name,
        command=command,
        path=path,
        content=_content_of(raw),
        output=raw.get("tool_output") or raw.get("output") or raw.get("result_json"),
        prompt=raw.get("prompt"),
        session_id=raw.get("conversation_id"),
        tool_use_id=raw.get("tool_use_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def _because(reason, note):
    """Keep the handler's own reason and add why the outcome changed shape.

    Replacing it would tell the user their rewrite was refused for wanting confirmation,
    which is a different and untrue story.
    """
    return "%s (%s)" % (reason, note) if reason else note


def _vendor_event(event):
    """The vendor event name, which `parse` keeps in `tool` when the tool has no name."""
    name = (event.raw or {}).get("hook_event_name")
    return name if name in EVENT_MAP else (event.tool if event.tool in EVENT_MAP else "beforeShellExecution")


def respond(decision, event):
    name = _vendor_event(event)

    if name in _MUTE:
        # Documented as supporting no output fields. Exit 0 and let the caller's own log
        # carry the finding -- pretending otherwise would invent a gate that isn't there.
        return "", 0

    if name in _POST_HOC:
        if decision.outcome in (DENY, ASK):
            note = "observed after the fact (%s cannot prevent it): %s" % (name, decision.reason or "policy violation")
            return _json.dumps({"additional_context": note}), 0
        return "", 0

    if name == "beforeSubmitPrompt":
        # This gate speaks `continue`, not `permission`.
        payload = {"continue": decision.outcome not in (DENY, ASK, REWRITE)}
        if decision.reason:
            payload["user_message"] = decision.reason
        return _json.dumps(payload), 0

    if name not in _PERMISSION_GATES:
        # sessionStart, stop, preCompact and friends: observation only.
        return "", 0

    honours_ask = _PERMISSION_GATES[name]
    payload = {}
    reason = decision.reason

    if decision.outcome == REWRITE:
        if name == "preToolUse" and decision.updated_input is not None:
            payload = {"permission": "allow", "updated_input": decision.updated_input}
        else:
            # Only preToolUse carries updated_input. Elsewhere a rewrite has no expression,
            # and allowing the *unmodified* input through would be the dangerous reading.
            payload = {"permission": "deny"}
            reason = _because(reason, "input requires modification, which this gate cannot express")
    elif decision.outcome == DENY:
        payload = {"permission": "deny"}
    elif decision.outcome == ASK:
        if honours_ask:
            payload = {"permission": "ask"}
        else:
            payload = {"permission": "deny"}
            note = (
                "%s cannot modify a tool call" % name
                if degraded_from(decision) == REWRITE
                else "%s cannot prompt for confirmation" % name
            )
            reason = _because(reason, "%s, so this is a block" % note)
    else:
        payload = {"permission": "allow"}

    if reason and payload.get("permission") != "allow":
        payload["user_message"] = reason
        payload["agent_message"] = reason
    return _json.dumps(payload), 0


#: Canonical event -> the vendor event that gates it most tightly. `pre_tool` maps to the
#: generic `preToolUse` rather than `beforeShellExecution`: it covers every tool, not just
#: shell, and it is the only one that can rewrite.
REVERSE_EVENT_MAP = {
    PRE_TOOL: "preToolUse",
    POST_TOOL: "postToolUse",
    TOOL_FAILURE: "postToolUseFailure",
    PROMPT_SUBMIT: "beforeSubmitPrompt",
    SESSION_START: "sessionStart",
    SESSION_END: "sessionEnd",
    SUBAGENT_START: "subagentStart",
    SUBAGENT_STOP: "subagentStop",
    STOP: "stop",
    PRE_COMPACT: "preCompact",
    FILE_CHANGED: "afterFileEdit",
}


def hook_config(canonical_events, command, matcher=None):
    hooks = {}
    for ev in canonical_events:
        name = REVERSE_EVENT_MAP.get(ev)
        if not name:
            continue
        entry = {"command": command}
        if matcher:
            entry["matcher"] = matcher
        # Fail open on a gate and a crashed hook silently permits the thing it was
        # installed to stop, so ask for fail-closed wherever a decision is expected.
        if name in _GATES:
            entry["failClosed"] = True
        hooks.setdefault(name, []).append(entry)
    return {"version": 1, "hooks": hooks}


CONFIG_PATH = ".cursor/hooks.json"
