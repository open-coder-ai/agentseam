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
    """Both send tool_input; only Codex sends turn_id/permission_mode. Confusing the
    two would send a Claude-shaped reply to an agent that names events differently."""
    assert A.adapters.detect(CX_WRITE) == "codex_cli"
    assert A.adapters.detect(CC_WRITE) == "claude_code"


def test_codex_parses_turn_scoped_payload():
    event = A.adapters.get("codex_cli").parse(CX_WRITE)
    assert event.tool_use_id == "tu-1"
    assert A.adapters.get("codex_cli").parse(CX_SHELL).command == "rm -rf /"


def test_a_codex_write_carries_no_path_or_content_only_a_command():
    """The whole write vocabulary this adapter used to read was Claude Code's, copied over
    on an assumption. Live capture (2026-08-28, 36 payloads) saw exactly two tool names --
    Bash and apply_patch -- and BOTH carry only tool_input.command. apply_patch IS the write
    tool, with the patch inside that string, so a content policy must gate on event.command
    here; event.content and event.path stay None on a real Codex write.
    """
    event = A.adapters.get("codex_cli").parse(CX_WRITE)
    assert event.tool == "apply_patch"
    assert event.content is None and event.path is None
    assert "AGENTS.md" in event.command


def test_codex_deny_is_json_with_exit_zero():
    """Codex wraps hooks in powershell -Command on Windows, collapsing exit 2 into 1;
    only the JSON decision means the same thing on every platform."""
    text, code, _, _ = A.handle(CX_WRITE, deny_all)
    out = json.loads(text)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert code == 0


def test_codex_echoes_pascalcase_event_name():
    """hook_config.rs's HookEventsToml and schema.rs's HookEventNameWire both use
    PascalCase, matching Claude Code's own convention -- not the camelCase this adapter
    used to assume (sourced from the App Server's separate IDE-facing protocol)."""
    text, _, _, _ = A.handle(CX_WRITE, deny_all)
    assert json.loads(text)["hookSpecificOutput"]["hookEventName"] == "PreToolUse"


def test_a_bare_allow_is_silence_because_codex_rejects_permissiondecision_allow():
    """output_parser.rs rejects permissionDecision:allow unless it carries updatedInput
    ("returned unsupported permissionDecision:allow"), and a rejected response is a hook
    error -- which fails OPEN. Silence is the only spelling of allow Codex accepts."""
    text, code, _, _ = A.handle(CX_WRITE, allow_all)
    assert text == "" and code == 0


def test_codex_degrades_ask_to_deny_because_the_vendor_rejects_it():
    """output_parser.rs's unsupported_pre_tool_use_hook_specific_output treats
    permissionDecision:ask as an invalid hook response, which Codex then fails OPEN on --
    so a real ask must not be sent as "ask" at all."""
    ask = json.loads(A.handle(CX_WRITE, lambda e: Decision.ask("confirm"))[0])
    assert ask["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "confirm" in ask["hookSpecificOutput"]["permissionDecisionReason"]


def test_codex_supports_rewrite():
    rw = json.loads(A.handle(CX_WRITE, lambda e: Decision.rewrite({"content": "safe"}))[0])
    assert rw["hookSpecificOutput"]["updatedInput"] == {"content": "safe"}


def test_a_rewrite_reason_reaches_the_model_not_just_the_replacement_input():
    """claude_code's respond already includes permissionDecisionReason on a rewrite; codex's
    dropped it entirely, so a handler explaining WHY a write was altered (e.g. 'secret
    redacted; use env var') left the model with the changed content and no explanation."""
    rw = json.loads(A.handle(CX_WRITE, lambda e: Decision.rewrite({"content": "safe"}, "secret redacted"))[0])
    assert rw["hookSpecificOutput"]["permissionDecisionReason"] == "secret redacted"

    # No reason supplied: the key stays absent rather than a fabricated placeholder.
    silent = json.loads(A.handle(CX_WRITE, lambda e: Decision.rewrite({"content": "safe"}))[0])
    assert "permissionDecisionReason" not in silent["hookSpecificOutput"]


def test_codex_hook_config_uses_matcher_group_shape():
    """The event key must be PascalCase ("PreToolUse"): HookEventsToml only recognises
    its twelve #[serde(rename = "PreToolUse")]-style keys and has no deny_unknown_fields,
    so a wrong-cased key like "preToolUse" is silently dropped -- the file parses fine and
    Codex loads zero hooks from it, no warning, no error."""
    cfg = A.adapters.get("codex_cli").hook_config([A.PRE_TOOL], '"C:\\py.exe" "guard.py"', matcher="Write")
    entry = cfg["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Write"
    assert entry["hooks"][0] == {
        "type": "command",
        "command": '"C:\\py.exe" "guard.py"',
        "commandWindows": '& "C:\\py.exe" "guard.py"',
    }


def test_windows_gets_a_powershell_callable_command():
    """Codex runs hooks through PowerShell on Windows, where a line beginning with a quoted
    path is a string expression, not an invocation -- a parse error, so nothing runs.
    Witnessed live (Codex CLI 0.150.1, 2026-08-28): the quoted form failed with "hook exited
    with code 1" and a `> file 2>&1` redirect on it produced no file at all; `&` fixed it.
    """
    mod = A.adapters.get("codex_cli")
    assert mod.powershell_command('"C:\\py.exe" "g.py" codex_cli') == '& "C:\\py.exe" "g.py" codex_cli'
    # Already callable: not doubled up.
    assert mod.powershell_command('& "C:\\py.exe" "g.py"') == '& "C:\\py.exe" "g.py"'


def test_prompt_submit_uses_the_block_dialect_not_the_pretooluse_gate():
    """UserPromptSubmitCommandOutputWire has `decision: BlockDecisionWire` and NO
    permissionDecision field, and every output struct is #[serde(deny_unknown_fields)] --
    so the gate shape is not ignored there, it makes Codex reject the whole response.
    Witnessed live: "hook returned invalid user prompt submit JSON output" on every prompt.
    """
    text, code, event, _ = A.handle(CX_LIVE_PROMPT_SUBMIT, deny_all)
    assert event.event == A.PROMPT_SUBMIT
    assert json.loads(text) == {"decision": "block", "reason": "test-deny"}
    assert code == 0

    # An allow at prompt_submit says nothing at all rather than a shape Codex would reject.
    assert A.handle(CX_LIVE_PROMPT_SUBMIT, allow_all)[0] == ""


def test_observation_only_events_stay_silent():
    """SessionStart accepts additionalContext but no decision, and SessionEnd has no output
    struct at all -- a verdict there is rejected, not merely ignored."""
    start = dict(CX_LIVE_PROMPT_SUBMIT, hook_event_name="SessionStart")
    assert A.handle(start, deny_all)[0] == ""


def test_session_start_is_declared_ambiguous_rather_than_answered_wrongly():
    """Codex sends no turn_id at SessionStart -- it is not turn-scoped, confirmed live and by
    SessionStartCommandInput, which is deny_unknown_fields and defines exactly these fields.
    Every one is a field Claude Code also sends, so nothing can separate them. Before this,
    a real Codex SessionStart was claimed by claude_code ALONE and answered confidently in
    the wrong dialect -- which Codex rejects, and a rejected response fails open. Declining
    is the honest answer; the consumer names the agent, as with tabnine and gemini_cli.
    """
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
    """Captured live from Codex CLI 0.150.1 (2026-08-28). Claude Code sends permission_mode
    and transcript_path too, so turn_id is what actually separates them."""
    assert A.adapters.detect(CX_LIVE_PROMPT_SUBMIT) == "codex_cli"
    event = A.adapters.get("codex_cli").parse(CX_LIVE_PROMPT_SUBMIT)
    assert event.event == A.PROMPT_SUBMIT and event.prompt == "<str:4>"
