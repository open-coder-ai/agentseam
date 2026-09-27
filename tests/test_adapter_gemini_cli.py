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


#: BeforeTool in the shape geminicli.com/docs/hooks/reference documents (read 2026-09-27): the
#: base input {session_id, transcript_path, cwd, hook_event_name, timestamp} plus the event's own.
GM_DOC_BEFORE_TOOL = {
    "session_id": "gm-1",
    "transcript_path": "/repo/.gemini/t.json",
    "cwd": "/repo",
    "hook_event_name": "BeforeTool",
    "timestamp": "2026-09-27T00:00:00.000Z",
    "tool_name": "run_shell_command",
    "tool_input": {"command": "rm -rf /"},
    "mcp_context": {},
    "original_request_name": "run_shell_command",
}


def test_a_documented_gemini_payload_parses_when_gemini_is_named():
    ev = A.adapters.get("gemini_cli").parse(GM_DOC_BEFORE_TOOL)
    assert (ev.event, ev.tool, ev.command, ev.session_id) == (A.PRE_TOOL, "run_shell_command", "rm -rf /", "gm-1")
    text, _code, _ev, _d = A.handle(GM_DOC_BEFORE_TOOL, lambda e: Decision.escalate("sure?"), agent="gemini_cli")
    assert json.loads(text) == {"decision": "ask", "reason": "sure?"}


def test_auto_detection_of_a_gemini_payload_is_never_weaker_than_gemini_itself():
    """Tabnine CLI sends Gemini's exact shape, timestamp included, so detect() cannot tell them
    apart. Declining would allow silently; resolving to Tabnine answers allow/deny identically
    and turns what only Gemini honours (ask, transform) into a deny -- stricter, never weaker."""
    assert A.adapters.detect(GM_DOC_BEFORE_TOOL) == "tabnine"
    for decision in (Decision.deny("no"), Decision.allow()):
        auto = A.handle(GM_DOC_BEFORE_TOOL, lambda e, d=decision: d)[:2]
        assert auto == A.handle(GM_DOC_BEFORE_TOOL, lambda e, d=decision: d, agent="gemini_cli")[:2]
    for decision in (Decision.escalate("sure?"), Decision.transform({"command": "ls"}, "safer")):
        text, _code, _ev, _d = A.handle(GM_DOC_BEFORE_TOOL, lambda e, d=decision: d)
        assert json.loads(text)["decision"] == "deny"
