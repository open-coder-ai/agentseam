"""Antigravity adapter: an event you have to infer, and a vocabulary richer than ours."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import AG_INVOCATION, AG_POST_TOOL, AG_PRE_TOOL, AG_STOP, AG_WRITE  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def deny_all(_e):
    return Decision.deny("test-deny")


def test_the_envelope_identifies_the_agent_even_though_no_event_is_named():
    assert "hookEventName" not in AG_PRE_TOOL and "hook_event_name" not in AG_PRE_TOOL
    assert A.adapters.detect(AG_PRE_TOOL) == "antigravity"


def test_pascalcase_tool_args_are_read_into_the_canonical_fields():
    _, _, event, _ = A.handle(AG_PRE_TOOL, deny_all)
    assert event.tool == "run_command"
    assert event.command == "npm test" and event.cwd == "/workspace/project"

    _, _, write, _ = A.handle(AG_WRITE, deny_all)
    assert write.path == "AGENTS.md" and "AWS_SECRET" in write.content


def test_stepidx_correlates_pre_and_post_tool_use():
    """The docstring's own pre/post correlation key -- PreToolUse and PostToolUse carry the"""
    _, _, event, _ = A.handle(AG_PRE_TOOL, deny_all)
    assert event.tool_use_id == "19"


def test_pre_tool_use_denies_with_a_reason():
    text, code, event, _ = A.handle(AG_PRE_TOOL, deny_all)
    assert event.event == A.PRE_TOOL
    assert json.loads(text) == {"decision": "deny", "reason": "test-deny"}
    assert code == 0


def test_ask_is_honoured_here_unlike_most_agents():
    text, _, _, _ = A.handle(AG_PRE_TOOL, lambda e: Decision.ask("confirm this"))
    assert json.loads(text) == {"decision": "ask", "reason": "confirm this"}


def test_a_degraded_rewrite_denies_rather_than_prompting():
    """Prompting would offer the user the *unmodified* call -- the thing the handler rejected."""
    text, _, _, _ = A.handle(AG_PRE_TOOL, lambda e: Decision.rewrite({"CommandLine": "true"}, "redact it"))
    body = json.loads(text)
    assert body["decision"] == "deny"
    assert "redact it" in body["reason"] and "cannot modify" in body["reason"]


def test_post_tool_use_is_told_apart_by_its_error_field_and_returns_empty():
    """The only signal separating the two, and it is documented as empty rather than absent."""
    text, code, event, _ = A.handle(AG_POST_TOOL, deny_all)
    assert event.event == A.POST_TOOL
    assert json.loads(text) == {} and code == 0


def test_an_unidentifiable_tool_payload_is_treated_as_pre_tool_use():
    """The tie is broken toward the gate on purpose."""
    ambiguous = {k: v for k, v in AG_POST_TOOL.items() if k != "error"}
    _, _, event, _ = A.handle(ambiguous, deny_all)
    assert event.event == A.PRE_TOOL


def test_stop_can_refuse_to_let_the_agent_stop():
    text, _, event, _ = A.handle(AG_STOP, lambda e: Decision.deny("tests still failing"))
    assert event.event == A.STOP
    assert json.loads(text) == {"decision": "continue", "reason": "tests still failing"}
    assert json.loads(A.handle(AG_STOP, lambda e: Decision.allow())[0])["decision"] == "stop"


def test_stop_names_why_ask_or_rewrite_became_continue():
    """Without the annotation, ASK/REWRITE at Stop read exactly like a DENY: 'continue' with"""
    ask = json.loads(A.handle(AG_STOP, lambda e: Decision.ask("confirm"))[0])
    assert ask["decision"] == "continue"
    assert "confirm" in ask["reason"] and "cannot prompt at Stop" in ask["reason"]

    rewrite = json.loads(A.handle(AG_STOP, lambda e: Decision.rewrite({"x": "y"}, "needs change"))[0])
    assert rewrite["decision"] == "continue"
    assert "needs change" in rewrite["reason"] and "cannot modify" in rewrite["reason"]


def test_invocation_events_are_unmapped_because_they_are_indistinguishable():
    """PreInvocation and PostInvocation carry identical fields, so nothing could tell them"""
    mod = A.adapters.get("antigravity")
    assert mod._infer_event(AG_INVOCATION) is None
    assert set(mod.REVERSE_EVENT_MAP) == {A.PRE_TOOL, A.POST_TOOL, A.STOP}


def test_hook_config_owns_one_named_group():
    """Antigravity keys hooks.json by hook name, which gives ownership a natural home."""
    mod = A.adapters.get("antigravity")
    config = mod.hook_config([A.PRE_TOOL], "guard.py", matcher="run_command")
    assert list(config) == ["agentseam"]
    entry = config["agentseam"]["PreToolUse"][0]
    assert entry["matcher"] == "run_command"
    assert entry["hooks"][0] == {"type": "command", "command": "guard.py"}


def test_antigravity_blocks_but_we_do_not_claim_it_fails_closed():
    """The documentation does not state a fail mode, so the weaker claim is recorded."""
    assert A.can_block("antigravity", A.PRE_TOOL)
    assert not A.can_rewrite("antigravity", A.PRE_TOOL)
    assert A.enforcement_level("antigravity", A.PRE_TOOL) == "best-effort"
    assert "not documented" in A.MATRIX["antigravity"]["notes"]
