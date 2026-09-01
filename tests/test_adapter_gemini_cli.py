"""Gemini CLI adapter: top-level decision, merging rewrite, Before*/After*."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import GM_AFTER, GM_REPLACE, GM_SHELL, GM_WRITE  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def allow_all(_e):
    return Decision.allow()


def deny_all(_e):
    return Decision.deny("test-deny")


def test_gemini_parses_its_own_tool_names():
    mod = A.adapters.get("gemini_cli")
    assert mod.parse(GM_WRITE).content == "team prefers pnpm"
    assert mod.parse(GM_REPLACE).content == "updated fact"
    assert mod.parse(GM_SHELL).command == "rm -rf /"
    assert mod.parse(GM_AFTER).event == A.POST_TOOL


def test_gemini_deny_is_top_level_not_nested():
    """Gemini puts decision at the top level; nesting it Claude-style would no-op."""
    text, code, _, _ = A.handle(GM_WRITE, deny_all)
    payload = json.loads(text)
    assert payload["decision"] == "deny"
    assert payload["reason"] == "test-deny"
    assert "hookSpecificOutput" not in payload
    assert code == 0


def test_gemini_rewrite_uses_hook_specific_tool_input():
    text, _, _, _ = A.handle(GM_WRITE, lambda e: Decision.rewrite({"content": "redacted"}))
    assert json.loads(text)["hookSpecificOutput"]["tool_input"] == {"content": "redacted"}


def test_gemini_ask_is_honoured_at_the_tool_gate():
    """This test asserted the opposite until 2026-08-28, and it was wrong."""
    text, _, _, _ = A.handle(GM_WRITE, lambda e: Decision.ask("needs a human"))
    payload = json.loads(text)
    assert payload["decision"] == "ask"
    assert payload["reason"] == "needs a human"


def test_gemini_ask_still_degrades_where_no_ask_is_read():
    """BeforeAgent consults only isBlockingDecision(), so an ask there is a word nothing"""
    raw = dict(GM_WRITE, hook_event_name="BeforeAgent", prompt="hello")
    text, _, _, _ = A.handle(raw, lambda e: Decision.ask("needs a human"))
    payload = json.loads(text)
    assert payload["decision"] == "deny"
    assert "confirmation required" in payload["reason"]


def test_gemini_allow():
    assert json.loads(A.handle(GM_WRITE, allow_all)[0])["decision"] == "allow"


def test_one_handler_covers_gemini_too():
    def handler(e):
        return Decision.deny("secret") if "SECRET" in (e.content or "") else Decision.allow()

    poisoned = json.loads(json.dumps(GM_WRITE))
    poisoned["tool_input"]["content"] = "SECRET"
    _t, _c, event, decision = A.handle(poisoned, handler)
    assert event.agent == "gemini_cli" and decision.outcome == "deny"
