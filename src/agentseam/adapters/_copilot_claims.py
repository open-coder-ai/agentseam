"""Who sent this: payload identification for VS Code Copilot (agent mode) and Copilot CLI.

Split from `vscode_copilot.py` by activity (the 300-line budget): this module decides whether
a payload is one of the two products' (`claims`, `is_cli_native`) and holds the event and tool
vocabularies that decision rests on; the adapter module reads the payload and answers it.
"""

from __future__ import annotations

from ..contract import (
    POST_TOOL,
    PRE_TOOL,
    PROMPT_SUBMIT,
    SESSION_END,
    SESSION_START,
    STOP,
    SUBAGENT_START,
    SUBAGENT_STOP,
    UNKNOWN,
)
from ._probes import event_keys_are_twins, looks_like_claude_code

EVENT_MAP = {
    "PreToolUse": PRE_TOOL,
    "PostToolUse": POST_TOOL,
    "UserPromptSubmit": PROMPT_SUBMIT,
    "SessionStart": SESSION_START,
    "SubagentStart": SUBAGENT_START,
    "SubagentStop": SUBAGENT_STOP,
    "Stop": STOP,
    "preToolUse": PRE_TOOL,
    "postToolUse": POST_TOOL,
    "userPromptSubmitted": PROMPT_SUBMIT,
    "sessionStart": SESSION_START,
    "sessionEnd": SESSION_END,
    "subagentStop": SUBAGENT_STOP,
    "agentStop": STOP,
}

MEMORY_TOOLS = ("memory", "copilot_memory")

_CODEX_MARKERS = ("turn_id", "permission_mode")

_CURSOR_MARKERS = ("model", "cursor_version", "conversation_id", "generation_id", "workspace_roots")

_CLAIMABLE = tuple(name for name in EVENT_MAP if name[:1].islower())

#: VS Code merges {timestamp, hook_event_name, session_id, transcript_path} into every payload
#: it sends (chatHookService.executeHook), so a PascalCase name under the snake_case key beside
#: `timestamp` is its envelope. It is only an envelope: a vendor whose own payload grows a
#: `timestamp` key (Grok Build ships one) must still win on its positive marks, so the claim
#: yields to every key another adapter identifies by. Codex's `permission_mode` and Cursor's
#: `model` are not among them: VS Code sends `model` at SessionStart, and permission_mode is
#: Claude's shape too, so only Droid's values of it count.
_VSCODE_ENVELOPE = "timestamp"
_SNAKE_EVENT_KEY = "hook_event_name"
#: Where either product spells its event name: VS Code under the snake_case key, the CLI camelCase.
EVENT_KEYS = (_SNAKE_EVENT_KEY, "hookEventName")
_FOREIGN_KEYS = (
    "turn_id",
    "cursor_version",
    "conversation_id",
    "generation_id",
    "workspace_roots",
    "project_path",
    "client_type",
)
#: Devin's marker; Claude Code (and so VS Code) may carry it too, beside fields Devin never sends.
_DEVIN_MARKER = "prompt_id"
#: Droid writes permission_mode from one mapping that returns only these (docs.factory.com/harness/hooks,
#: droid 0.238.0); the same five values are factory_droid's accept_values and claude_code's reject_values.
DROID_PERMISSION_MODES = ("off", "spec", "auto-low", "auto-medium", "auto-high")

#: Copilot CLI's own camelCase input (docs.github.com/en/copilot/reference/hooks-configuration,
#: read 2026-09-27): {sessionId, timestamp, cwd, toolName, toolArgs[, toolResult]} and no event
#: name at all. `toolArgs` is documented as the parsed arguments; the JSON-string form earlier
#: CLI builds sent is decoded too.
_CLI_ARGS = "toolArgs"
_CLI_RESULT = "toolResult"
_CLI_KEYS = (_CLI_ARGS, "toolName", "sessionId")

#: The camelCase `agentStop` payload (live capture, Windows, 2026-09-28): {sessionId, timestamp
#: (epoch ms), cwd, transcriptPath, stopReason, stop_hook_active} and no event name either.
_CLI_STOP = "stopReason"


def _name(raw):
    """The payload's own event name as text; None when it names none, UNKNOWN when the
    value is not text (a list or object cannot be looked up, and would raise if tried)."""
    if not isinstance(raw, dict):
        return None
    name = raw.get(EVENT_KEYS[0]) or raw.get(EVENT_KEYS[1])
    if name is None or isinstance(name, str):
        return name
    return UNKNOWN


def _foreign(raw):
    """True when the payload carries another vendor's positive self-identification."""
    if any(key in raw for key in _FOREIGN_KEYS) or raw.get("permission_mode") in DROID_PERMISSION_MODES:
        return True
    return _DEVIN_MARKER in raw and not looks_like_claude_code(raw)


def _envelope(raw, name):
    """VS Code's envelope, and nothing that says the payload is somebody else's."""
    return name in EVENT_MAP and _SNAKE_EVENT_KEY in raw and _VSCODE_ENVELOPE in raw and not _foreign(raw)


def _cli_shaped(raw):
    """A CLI call may omit toolArgs; unclaimed, it would pass unseen as "unrecognized"."""
    if _CLI_ARGS in raw or _CLI_STOP in raw:
        return True
    return "toolName" in raw and ("sessionId" in raw or _VSCODE_ENVELOPE in raw)


def claims(raw):
    """True for a payload from either product."""
    if not isinstance(raw, dict) or _is_grok_build(raw):
        return False
    name = _name(raw)
    if _envelope(raw, name):
        return True
    if any(k in raw for k in _CODEX_MARKERS + _CURSOR_MARKERS):
        return False
    if name in _CLAIMABLE:
        return True
    if name is None and _cli_shaped(raw):
        return True
    ti = raw.get("tool_input")
    return raw.get("tool_name") in MEMORY_TOOLS and isinstance(ti, dict) and "command" in ti


#: Grok Build's envelope: hookEventName is hook_event_name's snake_case twin (pre_tool_use, PreToolUse).
#: The probe itself, not a copy: the dialect bundle splices `_probes` in beside this module.
_is_grok_build = event_keys_are_twins


def is_cli_native(raw):
    """True for Copilot CLI's camelCase payloads, which get its top-level permission answer."""
    if not isinstance(raw, dict):
        return False
    name = _name(raw)
    if name is None:
        return any(k in raw for k in _CLI_KEYS)
    return name in _CLAIMABLE
