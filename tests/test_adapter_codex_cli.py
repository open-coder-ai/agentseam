"""Codex CLI adapter: Claude-shaped decisions, Claude-shaped PascalCase events, turn fields."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import CC_WRITE, CX_LIVE_PROMPT_SUBMIT, CX_SHELL, CX_WRITE  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def allow_all(_e):
    return Decision.allow()


def deny_all(_e):
    return Decision.deny("test-deny")


def test_codex_is_not_mistaken_for_claude():
    """Both send tool_input; only Codex sends turn_id/permission_mode. Confusing the"""
    assert A.adapters.detect(CX_WRITE) == "codex_cli"
    assert A.adapters.detect(CC_WRITE) == "claude_code"


def test_codex_parses_turn_scoped_payload():
    event = A.adapters.get("codex_cli").parse(CX_WRITE)
    assert event.tool_use_id == "tu-1"
    assert A.adapters.get("codex_cli").parse(CX_SHELL).command == "rm -rf /"


def test_a_codex_write_carries_no_path_or_content_only_a_command():
    """The whole write vocabulary this adapter used to read was Claude Code's, copied over"""
    event = A.adapters.get("codex_cli").parse(CX_WRITE)
    assert event.tool == "apply_patch"
    assert event.content is None and event.path is None
    assert "AGENTS.md" in event.command


def test_codex_deny_is_json_with_exit_zero():
    """Codex wraps hooks in powershell -Command on Windows, collapsing exit 2 into 1;"""
    text, code, _, _ = A.handle(CX_WRITE, deny_all)
    out = json.loads(text)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert code == 0


def test_codex_echoes_pascalcase_event_name():
    """hook_config.rs's HookEventsToml and schema.rs's HookEventNameWire both use"""
    text, _, _, _ = A.handle(CX_WRITE, deny_all)
    assert json.loads(text)["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_a_bare_allow_is_silence_because_codex_rejects_permissiondecision_allow():
    """output_parser.rs rejects permissionDecision:allow unless it carries updatedInput"""
    text, code, _, _ = A.handle(CX_WRITE, allow_all)
    assert text == "" and code == 0


def test_codex_degrades_ask_to_deny_because_the_vendor_rejects_it():
    """output_parser.rs's unsupported_pre_tool_use_hook_specific_output treats"""
    ask = json.loads(A.handle(CX_WRITE, lambda e: Decision.ask("confirm"))[0])
    assert ask["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "confirm" in ask["hookSpecificOutput"]["permissionDecisionReason"]


def test_codex_supports_rewrite():
    rw = json.loads(A.handle(CX_WRITE, lambda e: Decision.rewrite({"content": "safe"}))[0])
    assert rw["hookSpecificOutput"]["updatedInput"] == {"content": "safe"}


def test_a_rewrite_reason_reaches_the_model_not_just_the_replacement_input():
    """claude_code's respond already includes permissionDecisionReason on a rewrite; codex's"""
    rw = json.loads(A.handle(CX_WRITE, lambda e: Decision.rewrite({"content": "safe"}, "secret redacted"))[0])
    assert rw["hookSpecificOutput"]["permissionDecisionReason"] == "secret redacted"

    silent = json.loads(A.handle(CX_WRITE, lambda e: Decision.rewrite({"content": "safe"}))[0])
    assert "permissionDecisionReason" not in silent["hookSpecificOutput"]


def test_codex_hook_config_uses_matcher_group_shape():
    """The event key must be PascalCase ("PreToolUse"): HookEventsToml only recognises"""
    cfg = A.adapters.get("codex_cli").hook_config([A.PRE_TOOL], '"C:\\py.exe" "guard.py"', matcher="Write")
    entry = cfg["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Write"
    assert entry["hooks"][0] == {
        "type": "command",
        "command": '"C:\\py.exe" "guard.py"',
        "commandWindows": '& "C:\\py.exe" "guard.py"',
    }


def test_windows_gets_a_powershell_callable_command():
    """Codex runs hooks through PowerShell on Windows, where a line beginning with a quoted"""
    mod = A.adapters.get("codex_cli")
    assert mod.powershell_command('"C:\\py.exe" "g.py" codex_cli') == '& "C:\\py.exe" "g.py" codex_cli'
    assert mod.powershell_command('& "C:\\py.exe" "g.py"') == '& "C:\\py.exe" "g.py"'


def test_prompt_submit_uses_the_block_dialect_not_the_pretooluse_gate():
    """UserPromptSubmitCommandOutputWire has `decision: BlockDecisionWire` and NO"""
    text, code, event, _ = A.handle(CX_LIVE_PROMPT_SUBMIT, deny_all)
    assert event.event == A.PROMPT_SUBMIT
    assert json.loads(text) == {"decision": "block", "reason": "test-deny"}
    assert code == 0

    assert A.handle(CX_LIVE_PROMPT_SUBMIT, allow_all)[0] == ""


def test_observation_only_events_stay_silent():
    """SessionStart accepts additionalContext but no decision, and SessionEnd has no output"""
    start = dict(CX_LIVE_PROMPT_SUBMIT, hook_event_name="SessionStart")
    assert A.handle(start, deny_all)[0] == ""


def test_session_start_is_declared_ambiguous_rather_than_answered_wrongly():
    """Codex sends no turn_id at SessionStart -- it is not turn-scoped, confirmed live and by"""
    codex_session_start = {
        "hook_event_name": "SessionStart",
        "session_id": "s",
        "transcript_path": "/t",
        "cwd": "/repo",
        "model": "gpt-5-codex",
        "permission_mode": "default",
        "source": "startup",
    }
    assert A.adapters.get("codex_cli").claims(codex_session_start)
    assert A.adapters.detect(codex_session_start) is None, "a wrong dialect is worse than none"


def test_the_real_captured_payload_resolves_to_codex_alone():
    """Captured live from Codex CLI 0.150.1 (2026-08-28). Claude Code sends permission_mode"""
    assert A.adapters.detect(CX_LIVE_PROMPT_SUBMIT) == "codex_cli"
    event = A.adapters.get("codex_cli").parse(CX_LIVE_PROMPT_SUBMIT)
    assert event.event == A.PROMPT_SUBMIT and event.prompt == "<str:4>"
