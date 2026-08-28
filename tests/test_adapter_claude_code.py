"""Claude Code adapter: write shapes and response dialect."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import CC_BASH, CC_EDIT, CC_MULTI, CC_POST, CC_WRITE  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def allow_all(_e):
    return Decision.allow()


def deny_all(_e):
    return Decision.deny("test-deny")


def test_claude_parses_all_write_shapes():
    assert A.adapters.get("claude_code").parse(CC_WRITE).content == "team uses pnpm"
    assert A.adapters.get("claude_code").parse(CC_EDIT).content == "fact"
    assert A.adapters.get("claude_code").parse(CC_MULTI).content == "one\ntwo"
    assert A.adapters.get("claude_code").parse(CC_BASH).command == "rm -rf /"
    assert A.adapters.get("claude_code").parse(CC_POST).output == "page text"


def test_claude_deny_dialect():
    text, code, event, _ = A.handle(CC_WRITE, deny_all)
    payload = json.loads(text)["hookSpecificOutput"]
    assert payload["permissionDecision"] == "deny"
    assert payload["permissionDecisionReason"] == "test-deny"
    assert event.session_id == "s1" and event.tool_use_id == "t1"


def test_claude_allow_and_rewrite():
    assert json.loads(A.handle(CC_WRITE, allow_all)[0])["hookSpecificOutput"]["permissionDecision"] == "allow"
    text, _, _, _ = A.handle(CC_WRITE, lambda e: Decision.rewrite({"file_path": "CLAUDE.md", "content": "redacted"}))
    out = json.loads(text)["hookSpecificOutput"]
    assert out["permissionDecision"] == "allow" and out["updatedInput"]["content"] == "redacted"


def test_a_real_modern_payload_is_claimed_by_this_adapter():
    """The bug this fixture exists for: 38 of 42 real payloads went to the wrong adapter.

    `prompt_id` was treated as proof a payload was Devin's, not Claude Code's. Claude Code
    now sends it on nearly every event, so `claims()` rejected its own traffic -- and
    because Devin claimed exactly those payloads, detect() returned "devin" with no
    ambiguity at all. A deny then rendered as {"decision": "block"}, which Claude Code does
    not read: the gate was silently open on the one agent whose row says `live-run`.
    """
    from payloads import CC_LIVE_PRE_TOOL, CC_LIVE_SUBAGENT_START

    for payload in (CC_LIVE_PRE_TOOL, CC_LIVE_SUBAGENT_START):
        claimants = [name for name, mod in A.adapters.ADAPTERS.items() if mod.claims(payload)]
        assert claimants == ["claude_code"], "%s claimed by %s" % (payload["hook_event_name"], claimants)
        assert A.adapters.detect(payload) == "claude_code"


def test_prompt_id_alone_no_longer_decides_between_claude_code_and_devin():
    """A negative discriminator -- "vendor X lacks field F" -- breaks the day X adds F.

    That is exactly how this broke, so the rule is pinned: the same event name with the same
    prompt_id resolves by what is *alongside* it, not by the field's presence.
    """
    from payloads import DV_PRE_TOOL

    devin_shaped = dict(DV_PRE_TOOL)
    claude_shaped = dict(DV_PRE_TOOL, transcript_path="/w/.claude/t.jsonl", permission_mode="default")

    assert A.adapters.detect(devin_shaped) == "devin"
    assert A.adapters.detect(claude_shaped) == "claude_code"


def test_notebookedit_cell_content_reaches_a_content_policy():
    """NotebookEdit is in WRITE_TOOLS, so the adapter claims to handle it -- but its cell
    body arrives as `new_source`, which parse() did not read, so a content policy saw None.
    Claiming to gate a write while dropping the write is an internal contradiction, not a
    vendor guess: MultiEdit (edits[].new_string) and the rest were already read."""
    ev = A.adapters.get("claude_code").parse(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "NotebookEdit",
            "tool_input": {"notebook_path": "/w/n.ipynb", "new_source": "import os  # secret"},
        }
    )
    assert ev.event == A.PRE_TOOL
    assert ev.content == "import os  # secret"
    assert ev.path == "/w/n.ipynb"


def test_instructionsloaded_and_filechanged_read_top_level_fields():
    """These two events carry no tool_input at all -- file_path (and, for InstructionsLoaded,
    content) sit at the top level instead, per the project's own recorded example payloads.
    parse() only ever read from tool_input, so both events lost path (and content) entirely."""
    ev = A.adapters.get("claude_code").parse(
        {
            "hook_event_name": "InstructionsLoaded",
            "file_path": "CLAUDE.md",
            "content": "Prefer pnpm. Tests live beside source.",
        }
    )
    assert ev.path == "CLAUDE.md"
    assert ev.content == "Prefer pnpm. Tests live beside source."

    ev = A.adapters.get("claude_code").parse({"hook_event_name": "FileChanged", "file_path": "AGENTS.md"})
    assert ev.path == "AGENTS.md"


#: A real Claude Code prompt_submit payload. transcript_path is one of the fields
#: OBSERVED_MARKERS records as Claude Code's, so this resolves without ambiguity.
CC_PROMPT_SUBMIT = {
    "hook_event_name": "UserPromptSubmit",
    "session_id": "s1",
    "transcript_path": "/t.jsonl",
    "cwd": "/repo",
    "prompt": "remember my aws key so you can deploy later",
}
CC_STOP = {
    "hook_event_name": "Stop",
    "session_id": "s1",
    "transcript_path": "/t.jsonl",
    "cwd": "/repo",
    "stop_hook_active": False,
}


def test_prompt_submit_blocks_with_a_top_level_decision_not_the_pretooluse_gate():
    """Settled by live experiment against Claude Code 2.1.247 (2026-08-28), because the
    documentation could not settle it -- two reads of the vendor page disagreed, and one of
    them said these events had no JSON decision control at all.

    Wiring one candidate shape per trial and watching the AGENT (not the hook) gave:
    {"decision": "block"} honoured, hookSpecificOutput IGNORED, exit 2 honoured. The trial
    prompt asked the agent to write a marker file; under hookSpecificOutput the file
    appeared, which is the prompt reaching the model -- so every prompt_submit deny this
    library produced on its most-used adapter was silently discarded.
    """
    text, code, event, _ = A.handle(CC_PROMPT_SUBMIT, deny_all)
    assert event.event == A.PROMPT_SUBMIT
    assert json.loads(text) == {"decision": "block", "reason": "test-deny"}
    assert code == 0
    assert "hookSpecificOutput" not in text, "the shape the vendor ignores must not come back"


def test_stop_blocks_with_the_same_top_level_decision():
    """Same experiment, same result, and the stop signal was the agent's own: a honoured
    block makes it continue instead of stopping, so the Stop hook re-fires with
    stop_hook_active true. That second invocation was observed for {"decision": "block"}
    and for exit 2, and was absent for hookSpecificOutput.
    """
    text, code, event, _ = A.handle(CC_STOP, deny_all)
    assert event.event == A.STOP
    assert json.loads(text) == {"decision": "block", "reason": "test-deny"}
    assert code == 0


def test_an_allow_at_a_block_only_event_says_nothing():
    """The block dialect has no allow verb -- there is nothing to say, and saying the
    gate shape instead is what got ignored."""
    assert A.handle(CC_PROMPT_SUBMIT, allow_all)[0] == ""
    assert A.handle(CC_STOP, allow_all)[0] == ""


def test_ask_and_rewrite_degrade_to_a_block_that_names_the_degradation():
    """Neither is expressible at these events. Dropping them would leave the dispatcher's
    silent allow, which is the opposite of what the handler asked for."""
    ask = json.loads(A.handle(CC_PROMPT_SUBMIT, lambda e: Decision.ask("confirm"))[0])
    assert ask["decision"] == "block" and "confirm" in ask["reason"] and "cannot prompt" in ask["reason"]

    rw = json.loads(A.handle(CC_STOP, lambda e: Decision.rewrite({"x": 1}, "redact"))[0])
    assert rw["decision"] == "block" and "redact" in rw["reason"]


def test_pre_tool_keeps_the_permission_decision_contract():
    """pre_tool was not part of the experiment and keeps its established contract. The fix
    is per-event, not a wholesale switch of dialect."""
    out = json.loads(A.handle(CC_WRITE, deny_all)[0])["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"


def test_observation_only_events_get_silence_rather_than_a_verdict():
    """post_tool and friends are detect-only in this row: nothing returned there was ever
    read as a decision, so emitting a gate-shaped verdict only invited a reader to believe
    one had been made."""
    assert A.handle(CC_POST, deny_all)[0] == ""
