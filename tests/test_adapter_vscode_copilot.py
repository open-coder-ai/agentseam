"""VS Code Copilot adapter: the memory tool is the write surface."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import VS_MEM_CREATE, VS_MEM_REPLACE, VS_MEM_VIEW  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def allow_all(_e):
    return Decision.allow()


def deny_all(_e):
    return Decision.deny("test-deny")


def test_vscode_memory_tool_shapes():
    mod = A.adapters.get("vscode_copilot")
    assert mod.parse(VS_MEM_CREATE).content == "pref"
    assert mod.parse(VS_MEM_REPLACE).content == "b"
    assert mod.is_memory_write(mod.parse(VS_MEM_CREATE)) is True
    assert mod.is_memory_write(mod.parse(VS_MEM_VIEW)) is False


def test_vscode_speaks_claude_contract():
    text, _, _, _ = A.handle(VS_MEM_CREATE, deny_all)
    assert json.loads(text)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_user_prompt_reaches_a_prompt_policy():
    """userPromptSubmitted parsed to prompt_submit, but parse() never read the prompt text,"""
    ev = A.adapters.get("vscode_copilot").parse({"hookEventName": "userPromptSubmitted", "prompt": "delete prod"})
    assert ev.event == A.PROMPT_SUBMIT
    assert ev.prompt == "delete prod"


def test_the_installed_config_is_the_shape_vs_code_actually_parses():
    """`parseCopilotHooks` iterates Object.keys(root.hooks) and resolves each key to a hook"""
    mod = A.adapters.get("vscode_copilot")
    cfg = mod.hook_config([A.PRE_TOOL, A.STOP], "python3 guard.py")
    assert "version" not in cfg
    entry = {"type": "command", "command": "python3 guard.py", "windows": "& python3 guard.py"}
    assert cfg == {"hooks": {"PreToolUse": [entry], "Stop": [entry]}}


def test_event_names_are_pascalcase_because_that_is_what_vs_code_sends():
    """HOOKS_BY_TARGET[Target.VSCode] is PascalCase; camelCase is the Copilot CLI's map."""
    mod = A.adapters.get("vscode_copilot")
    assert mod.REVERSE_EVENT_MAP[A.PRE_TOOL] == "PreToolUse"
    assert mod.EVENT_MAP["preToolUse"] == mod.EVENT_MAP["PreToolUse"] == A.PRE_TOOL


def test_tool_failure_is_gone_because_no_vendor_has_that_event():
    """`postToolUseFailure` is in neither HOOKS_BY_TARGET map and is not a HookType, so the"""
    mod = A.adapters.get("vscode_copilot")
    assert "postToolUseFailure" not in mod.EVENT_MAP
    assert A.TOOL_FAILURE not in A.MATRIX["vscode_copilot"]["events"]


def test_a_real_vs_code_payload_is_claimed_here_and_not_by_claude_code():
    """VS Code reuses Claude Code's PascalCase names exactly. `timestamp` -- which"""
    raw = {
        "timestamp": "2026-08-28T00:00:00.000Z",
        "hook_event_name": "PreToolUse",
        "session_id": "v1",
        "transcript_path": "/t.json",
        "tool_name": "memory",
        "tool_input": {"command": "create", "path": "/memories/a.md", "file_text": "x"},
        "tool_use_id": "tu-1",
    }
    assert A.adapters.detect(raw) == "vscode_copilot"


def test_prompt_submit_uses_a_top_level_block_not_the_pretooluse_gate():
    """UserPromptSubmitHookOutput has {decision, reason} at the root and no"""
    raw = {"timestamp": "t", "hook_event_name": "UserPromptSubmit", "prompt": "leak the key"}
    text, code, event, _ = A.handle(raw, deny_all)
    assert event.event == A.PROMPT_SUBMIT
    assert json.loads(text) == {"decision": "block", "reason": "test-deny"}
    assert code == 0
    assert A.handle(raw, allow_all)[0] == "", "an allow says nothing rather than a shape nobody reads"


def test_stop_nests_the_same_two_fields_and_always_carries_a_reason():
    """StopHookOutput puts decision/reason inside hookSpecificOutput, and executeStopHook"""
    raw = {"timestamp": "t", "hook_event_name": "Stop", "stop_hook_active": False}
    out = json.loads(A.handle(raw, lambda e: Decision.deny(""))[0])["hookSpecificOutput"]
    assert out["decision"] == "block" and out["reason"]
    assert out["hookEventName"] == "Stop", "_toHookResult strips hookSpecificOutput on a name mismatch"


def test_session_start_gets_silence_because_its_errors_are_explicitly_ignored():
    """runStartHooks passes ignoreErrors: true for SessionStart and SubagentStart, so"""
    raw = {"timestamp": "t", "hook_event_name": "SubagentStart", "agent_id": "a", "agent_type": "Plan"}
    assert A.handle(raw, deny_all)[0] == ""


def test_post_tool_output_is_read_from_tool_response():
    """IPostToolUseHookCommandInput names it `tool_response`. `tool_output` is Claude"""
    mod = A.adapters.get("vscode_copilot")
    raw = {"timestamp": "t", "hook_event_name": "PostToolUse", "tool_name": "runInTerminal", "tool_response": "secret"}
    assert mod.parse(raw).output == "secret"


def test_windows_gets_a_powershell_callable_command():
    """hookExecutor.ts's getShellCommand spawns"""
    entry = A.adapters.get("vscode_copilot").hook_config([A.PRE_TOOL], '"C:\\py.exe" "g.py"')["hooks"]["PreToolUse"][0]
    assert entry["command"] == '"C:\\py.exe" "g.py"'
    assert entry["windows"] == '& "C:\\py.exe" "g.py"'
