"""Example payloads for the vendors that name the event under a key of their own.

Split from `vendor_payloads.py` by activity (the 300-line budget): goose (`event`), openhands
(`event_type`), mistral_vibe (its own hook types under `hook_event_name`) and cline (`hookName`).
"""

from __future__ import annotations

from payload_story import FAILING, FAILURE, MEMORY_FILE, PROMPT, SECRET

from agentseam.contract import FILE_CHANGED, POST_TOOL, PRE_TOOL, PROMPT_SUBMIT, SESSION_START, STOP, TOOL_FAILURE


def goose(event, vendor_event, base):
    """The event name rides under `event`; `matcher_context` is what the rule's regex saw."""
    raw = dict(base, event=vendor_event)
    if event in (PRE_TOOL, POST_TOOL, TOOL_FAILURE):
        raw["working_dir"] = "/repo"
        raw["tool_call_id"] = "call-1"
        if event == PRE_TOOL:
            raw.update(tool_name="write", tool_input={"path": MEMORY_FILE, "content": SECRET})
        else:
            raw.update(tool_name="shell", tool_input={"command": FAILING})
        raw["matcher_context"] = raw["tool_name"]
    elif event == PROMPT_SUBMIT:
        raw.update(message=PROMPT, matcher_context=PROMPT)
    elif event == FILE_CHANGED:
        raw["matcher_context"] = MEMORY_FILE
    elif event == STOP:
        raw["last_assistant_message"] = "Done."
    return raw


def openhands(event, vendor_event, base):
    """The event name rides under `event_type`; the cwd is `working_dir`."""
    raw = dict(base, event_type=vendor_event, working_dir="/repo")
    if event == PRE_TOOL:
        raw.update(tool_name="file_editor", tool_input={"command": "create", "path": MEMORY_FILE, "file_text": SECRET})
    elif event == POST_TOOL:
        raw.update(tool_name="terminal", tool_input={"command": FAILING}, tool_response={"exit_code": 1})
    elif event == PROMPT_SUBMIT:
        raw["message"] = PROMPT
    return raw


def mistral_vibe(event, vendor_event, base):
    """Vibe's snake_case hook type under hook_event_name; tool calls carry tool_call_id."""
    raw = dict(base, hook_event_name=vendor_event, cwd="/repo")
    if event == PRE_TOOL:
        raw.update(tool_name="write_file", tool_call_id="c1", tool_input={"file_path": MEMORY_FILE, "content": SECRET})
    elif event == POST_TOOL:
        raw.update(tool_name="bash", tool_call_id="c2", tool_input={"command": FAILING}, tool_status="failure")
        raw.update(tool_output=None, tool_output_text=FAILURE, tool_error=FAILURE, duration_ms=1200)
    return raw


def cline(event, vendor_event, base):
    """The documented file name under hookName, and one camelCase object per event; every
    non-string tool argument arrives as JSON text."""
    raw = dict(base, hookName=vendor_event, workspaceRoots=["/repo"])
    if event == PRE_TOOL:
        raw["preToolUse"] = {"toolName": "write_to_file", "parameters": {"path": MEMORY_FILE, "content": SECRET}}
    elif event == POST_TOOL:
        params = {"commands": '["%s"]' % FAILING}
        raw["postToolUse"] = {"toolName": "run_commands", "parameters": params, "result": FAILURE}
        raw["postToolUse"].update(success=False, executionTimeMs=1200)
    elif event == PROMPT_SUBMIT:
        raw["userPromptSubmit"] = {"prompt": PROMPT, "attachments": []}
    elif event == SESSION_START:
        raw["taskStart"] = {"taskMetadata": {"taskId": "example", "ulid": "example", "initialTask": PROMPT}}
    elif event == STOP:
        raw["taskComplete"] = {"taskMetadata": {"taskId": "example", "ulid": "example"}}
    return raw
