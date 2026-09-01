"""Windsurf adapter: exit-code-only blocking, and no file-write surface at all."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import WS_COMMAND, WS_POST_MCP, WS_PROMPT  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def allow_all(_e):
    return Decision.allow()


def deny_all(_e):
    return Decision.deny("test-deny")


def test_parses_terminal_and_prompt_payloads():
    mod = A.adapters.get("windsurf")
    assert mod.parse(WS_COMMAND).command == "rm -rf /"
    assert mod.parse(WS_COMMAND).session_id == "traj-1"
    assert mod.parse(WS_PROMPT).prompt == "delete everything"
    assert mod.parse(WS_PROMPT).event == A.PROMPT_SUBMIT


def test_pre_hooks_block_with_exit_two_and_a_reason_on_stderr():
    """Exit code is the only channel; the reason still has to reach a human."""
    text, code, _, _ = A.handle(WS_COMMAND, deny_all)
    assert code == 2
    assert "test-deny" in text


def test_prompt_hook_can_block_too():
    _text, code, _, _ = A.handle(WS_PROMPT, deny_all)
    assert code == 2


def test_post_hooks_cannot_block_and_say_so():
    """A post hook returning 2 would imply prevention that did not happen."""
    text, code, event, _ = A.handle(WS_POST_MCP, deny_all)
    assert event.event == A.POST_TOOL
    assert code == 0
    assert "cannot block" in text


def test_allow_is_silent():
    assert A.handle(WS_COMMAND, allow_all)[:2] == ("", 0)


def test_rewrite_blocks_rather_than_passing_input_through():
    """No rewrite channel exists; letting the original input run would be the bug."""
    text, code, _, _ = A.handle(WS_COMMAND, lambda e: Decision.rewrite({"command": "true"}))
    assert code == 2
    assert "cannot rewrite" in text
    assert "input requires modification" in text


def test_mcp_events_expose_the_tool_identity_not_the_vendor_event_name():
    """A cross-agent handler written as `event.tool in RISKY_TOOLS` (works on"""
    ev = A.adapters.get("windsurf").parse(WS_POST_MCP)
    assert ev.tool == "docs/fetch"


def test_pre_mcp_tool_use_still_blocks_after_losing_its_place_in_event_tool():
    """Blocking must not silently break once event.tool stops doubling as the vendor"""
    pre_mcp = {
        "hook_event_name": "pre_mcp_tool_use",
        "trajectory_id": "traj-4",
        "tool_info": {"server": "docs", "tool": "fetch"},
    }
    text, code, event, _ = A.handle(pre_mcp, deny_all)
    assert event.event == A.PRE_TOOL
    assert code == 2 and "test-deny" in text


def test_install_wires_both_pre_tool_gates_not_just_the_shell_one():
    """pre_mcp_tool_use is a documented BLOCKING gate mapped to PRE_TOOL, same as"""
    mod = A.adapters.get("windsurf")
    rules = mod.hook_config([A.PRE_TOOL], "guard.py")["hooks"]
    assert "pre_run_command" in rules and "pre_mcp_tool_use" in rules


def test_matrix_records_that_no_file_write_event_exists():
    """The absence is the point: a memory-file write is invisible to a Windsurf hook,"""
    row = A.MATRIX["windsurf"]
    assert A.FILE_CHANGED not in row["events"]
    assert "NO file-write event" in row["notes"]
    assert A.enforcement_level("windsurf", A.PRE_TOOL) == "best-effort"
