"""Cursor adapter.

Two dialects in one agent, and the difference is the whole honesty story:
  beforeShellExecution / beforeMCPExecution -> TRUE pre-execution block; response is
      {"permission": "allow"|"deny"|"ask", "user_message", "agent_message"}; exit 2 also denies.
  afterFileEdit -> fires AFTER the write landed. Audit only: exit 0 clean / 2 flagged.
Verified against Cursor's own hook example repo (hooks.json + scripts + test fixtures).
"""

from __future__ import annotations

from ..contract import (Event, ASK, DENY, REWRITE, PRE_TOOL, POST_TOOL, PROMPT_SUBMIT,
                        SESSION_START, STOP, PRE_COMPACT)

AGENT = "cursor"

EVENT_MAP = {
    "beforeShellExecution": PRE_TOOL,
    "beforeMCPExecution": PRE_TOOL,
    "afterFileEdit": POST_TOOL,
    "afterShellExecution": POST_TOOL,
    "beforeSubmitPrompt": PROMPT_SUBMIT,
    "sessionStart": SESSION_START,
    "stop": STOP,
    "preCompact": PRE_COMPACT,
}

# Cursor does not always name the event in the payload; these shapes identify it.
def claims(raw):
    if not isinstance(raw, dict):
        return False
    if raw.get("hook_event_name") in EVENT_MAP:
        return True
    # beforeShellExecution: top-level command alongside cwd/sandbox (not Claude's nesting)
    if isinstance(raw.get("command"), str) and ("cwd" in raw or "sandbox" in raw):
        return True
    # afterFileEdit: file_path + edits[]
    return "file_path" in raw and isinstance(raw.get("edits"), list)


def parse(raw):
    name = raw.get("hook_event_name")
    if name in EVENT_MAP:
        event = EVENT_MAP[name]
    elif "file_path" in raw and isinstance(raw.get("edits"), list):
        event = POST_TOOL
        name = "afterFileEdit"
    else:
        event = PRE_TOOL
        name = name or "beforeShellExecution"
    content = None
    if isinstance(raw.get("edits"), list):
        joined = "\n".join(str(e.get("new_string", "")) for e in raw["edits"])
        content = joined or None
    return Event(
        AGENT, event,
        tool=name,
        command=raw.get("command"),
        path=raw.get("file_path"),
        content=content,
        session_id=raw.get("conversation_id") or raw.get("session_id"),
        cwd=raw.get("cwd"),
        raw=raw,
    )


def respond(decision, event):
    import json as _json
    vendor_event = event.tool or ""
    post_write = vendor_event.startswith("after")
    if post_write:
        # No pre-write gate exists here. A deny becomes a recorded detection, and we
        # say so in the message rather than implying the write was stopped.
        if decision.outcome in (DENY, ASK):
            msg = "flagged post-write (Cursor cannot block file edits): %s" % (decision.reason or "policy violation")
            return _json.dumps({"user_message": msg, "agent_message": msg}), 2
        return "", 0
    if decision.outcome == DENY:
        payload = {"permission": "deny"}
    elif decision.outcome == ASK:
        payload = {"permission": "ask"}
    elif decision.outcome == REWRITE:
        # Cursor has no updatedInput; the honest translation is to ask rather than
        # silently let the unmodified input through.
        payload = {"permission": "ask"}
    else:
        payload = {"permission": "allow"}
    if decision.reason:
        payload["user_message"] = decision.reason
        payload["agent_message"] = decision.reason
    return _json.dumps(payload), 0


def hook_config(canonical_events, command, matcher=None):
    reverse = {PRE_TOOL: "beforeShellExecution", POST_TOOL: "afterFileEdit",
               PROMPT_SUBMIT: "beforeSubmitPrompt", SESSION_START: "sessionStart", STOP: "stop"}
    hooks = {}
    for ev in canonical_events:
        name = reverse.get(ev)
        if name:
            hooks.setdefault(name, []).append({"command": command})
    return {"version": 1, "hooks": hooks}


CONFIG_PATH = ".cursor/hooks.json"
