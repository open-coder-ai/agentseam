"""Codex CLI adapter: Claude-shaped decisions, camelCase events, turn fields."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import CC_WRITE, CX_SHELL, CX_WRITE  # noqa: E402

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
    assert event.content == "team fact"
    assert event.path == "AGENTS.md"
    assert event.tool_use_id == "tu-1"
    assert A.adapters.get("codex_cli").parse(CX_SHELL).command == "rm -rf /"


def test_codex_deny_is_json_with_exit_zero():
    """Codex wraps hooks in powershell -Command on Windows, collapsing exit 2 into 1;
    only the JSON decision means the same thing on every platform."""
    text, code, _, _ = A.handle(CX_WRITE, deny_all)
    out = json.loads(text)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert code == 0


def test_codex_echoes_camelcase_event_name():
    text, _, _, _ = A.handle(CX_WRITE, allow_all)
    assert json.loads(text)["hookSpecificOutput"]["hookEventName"] == "preToolUse"


def test_codex_supports_ask_and_rewrite():
    ask = json.loads(A.handle(CX_WRITE, lambda e: Decision.ask("confirm"))[0])
    assert ask["hookSpecificOutput"]["permissionDecision"] == "ask"
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
    cfg = A.adapters.get("codex_cli").hook_config([A.PRE_TOOL], "handler", matcher="Write")
    entry = cfg["hooks"]["preToolUse"][0]
    assert entry["matcher"] == "Write"
    assert entry["hooks"][0] == {"type": "command", "command": "handler"}
