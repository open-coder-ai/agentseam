"""Devin adapter, and the ambiguity it creates with Claude Code.

Devin reuses Claude Code's event names and payload shape, so half of these tests are about
detection rather than behaviour: if two adapters claim one payload the dispatcher cannot
name the agent, and an unidentified payload is allowed through.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import CC_BASH, DV_PERMISSION, DV_PRE_TOOL, DV_PROMPT, DV_SESSION_START, DV_WRITE  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def deny_all(_e):
    return Decision.deny("test-deny")


def test_prompt_id_separates_devin_from_claude_code():
    assert A.adapters.detect(DV_PRE_TOOL) == "devin"
    assert A.adapters.detect(CC_BASH) == "claude_code"


def test_a_devin_only_event_identifies_devin_without_prompt_id():
    assert A.adapters.detect(DV_PERMISSION) == "devin"


def test_session_start_is_ambiguous_and_nobody_guesses():
    """prompt_id is documented as absent before the first user prompt, so this payload is
    indistinguishable from Claude Code's -- and from Gemini CLI's, which spells the event the
    same way. Devin's own adapter therefore declines it, and the two that do claim it are
    enough to make `detect` refuse. Note what this rules out: a lone claimant would have
    been answered confidently and wrongly.
    """
    claimants = sorted(n for n, m in A.adapters.ADAPTERS.items() if m.claims(DV_SESSION_START))
    assert claimants == ["claude_code", "gemini_cli"]
    assert A.adapters.detect(DV_SESSION_START) is None
    # Naming the agent still works, which is the documented way out.
    _, _, event, _ = A.handle(DV_SESSION_START, lambda e: Decision.allow(), agent="devin")
    assert event.agent == "devin" and event.event == A.SESSION_START


def test_devin_blocks_with_a_top_level_decision_not_permission_decision():
    text, code, event, _ = A.handle(DV_PRE_TOOL, deny_all)
    body = json.loads(text)
    assert event.event == A.PRE_TOOL and event.command == "rm -rf /"
    assert body == {"decision": "block", "reason": "test-deny"}
    assert "hookSpecificOutput" not in body and code == 0


def test_ask_becomes_a_block_and_says_so():
    """Devin's vocabulary is approve or block. Allowing through would invert the intent."""
    text, _, _, _ = A.handle(DV_PRE_TOOL, lambda e: Decision.ask("needs review"))
    body = json.loads(text)
    assert body["decision"] == "block"
    assert "needs review" in body["reason"] and "cannot prompt" in body["reason"]


def test_rewrite_uses_hook_specific_output_and_merges():
    text, _, _, _ = A.handle(DV_WRITE, lambda e: Decision.rewrite({"content": "redacted"}))
    body = json.loads(text)["hookSpecificOutput"]
    assert body["hookEventName"] == "PreToolUse"
    # updatedInput is merged into the tool's arguments, so a partial object is correct.
    assert body["updatedInput"] == {"content": "redacted"}


def test_a_write_payload_exposes_its_path_and_content():
    _, _, event, _ = A.handle(DV_WRITE, deny_all)
    assert event.path == "AGENTS.md" and "AWS_SECRET" in event.content


def test_prompt_submit_can_inject_context_on_allow():
    text, _, event, _ = A.handle(DV_PROMPT, lambda e: Decision.allow("deploys need a ticket"))
    body = json.loads(text)["hookSpecificOutput"]
    assert event.event == A.PROMPT_SUBMIT
    assert body["hookEventName"] == "UserPromptSubmit"
    assert body["additionalContext"] == "deploys need a ticket"


def test_hook_config_writes_devins_own_file_not_claude_codes():
    """Devin reads .claude/settings.json too, but our entry must be removable on its own."""
    mod = A.adapters.get("devin")
    assert mod.CONFIG_PATH == ".devin/hooks.v1.json"
    config = mod.hook_config([A.PRE_TOOL], "handler.py", matcher="exec")
    assert config["PreToolUse"][0]["matcher"] == "exec"
    assert config["PreToolUse"][0]["hooks"][0] == {"type": "command", "command": "handler.py"}


def test_devin_pre_tool_is_best_effort_because_it_fails_open():
    """Only exit 2 blocks; other non-zero codes are logged and the action proceeds."""
    assert A.can_block("devin", A.PRE_TOOL)
    assert A.enforcement_level("devin", A.PRE_TOOL) == "best-effort"
