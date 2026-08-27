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
