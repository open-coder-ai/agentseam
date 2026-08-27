"""Cursor adapter: a generic pre-tool gate that can also rewrite, plus surfaces that cannot.

Cursor is the agent where "what can this actually enforce" varies most by which of its hook
events you are standing on, so most of these tests are about the seams between them.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import CU_EDIT, CU_PRE_TOOL, CU_READ, CU_SHELL, CU_SUBMIT  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def allow_all(_e):
    return Decision.allow()


def deny_all(_e):
    return Decision.deny("test-deny")


def ask_all(_e):
    return Decision.ask("confirm please")


def test_cursor_shell_blocks_pre_execution():
    text, code, event, _ = A.handle(CU_SHELL, deny_all)
    assert json.loads(text)["permission"] == "deny"
    assert event.event == A.PRE_TOOL and code == 0


def test_pre_tool_use_gates_a_file_write_before_it_lands():
    """The generic preToolUse hook fires for every tool, so writes are blockable after all."""
    text, code, event, _ = A.handle(CU_PRE_TOOL, deny_all)
    assert event.event == A.PRE_TOOL
    assert event.path == "CLAUDE.md" and "AWS_SECRET" in event.content
    assert json.loads(text)["permission"] == "deny"
    assert code == 0


def test_pre_tool_use_carries_a_rewrite():
    text, _, _, _ = A.handle(CU_PRE_TOOL, lambda e: Decision.rewrite({"content": "redacted"}))
    body = json.loads(text)
    assert body["permission"] == "allow"
    assert body["updated_input"] == {"content": "redacted"}


def test_a_rewrite_on_the_shell_gate_denies_rather_than_letting_the_original_run():
    """Only preToolUse takes updated_input. Allowing the unmodified command would be worse."""
    text, _, _, _ = A.handle(CU_SHELL, lambda e: Decision.rewrite({"command": "true"}))
    body = json.loads(text)
    assert body["permission"] == "deny"
    assert "cannot express" in body["user_message"]


def test_ask_is_honoured_on_the_shell_gate_and_denied_on_pre_tool_use():
    """Cursor accepts "ask" in the preToolUse schema but does not enforce it today.

    Returning it there would read as a prompt and behave as a pass, so it becomes a deny.
    """
    shell, _, _, _ = A.handle(CU_SHELL, ask_all)
    assert json.loads(shell)["permission"] == "ask"

    generic = json.loads(A.handle(CU_PRE_TOOL, ask_all)[0])
    assert generic["permission"] == "deny"
    assert "cannot prompt" in generic["agent_message"]


def test_before_read_file_can_block_a_secret_from_reaching_the_model():
    text, _, event, _ = A.handle(CU_READ, deny_all)
    assert event.event == A.PRE_TOOL and event.path == "/repo/.env"
    assert json.loads(text)["permission"] == "deny"


def test_before_submit_prompt_speaks_continue_not_permission():
    text, _, event, _ = A.handle(CU_SUBMIT, deny_all)
    body = json.loads(text)
    assert event.event == A.PROMPT_SUBMIT
    assert body["continue"] is False and "permission" not in body
    assert json.loads(A.handle(CU_SUBMIT, allow_all)[0])["continue"] is True


def test_after_file_edit_is_post_write_and_has_no_output_contract():
    """The write already landed and Cursor documents no output fields, so we stay silent.

    Emitting JSON with an exit code here would imply a gate that does not exist.
    """
    text, code, event, _ = A.handle(CU_EDIT, deny_all)
    assert event.event == A.FILE_CHANGED
    assert (text, code) == ("", 0)


def test_cursor_clean_edit_is_silent():
    text, code, _, _ = A.handle(CU_EDIT, allow_all)
    assert (text, code) == ("", 0)


def test_post_tool_use_failure_gets_the_same_detection_record_as_its_sibling():
    """postToolUseFailure was missing from _POST_HOC, so a deny/ask at a failed tool call
    returned silence instead of the additional_context record postToolUse itself gets --
    the identical fact (the call already happened) went unrecorded on its failure twin."""
    raw = dict(CU_PRE_TOOL, hook_event_name="postToolUseFailure")
    text, code, event, _ = A.handle(raw, deny_all)
    assert event.event == A.TOOL_FAILURE
    assert code == 0
    body = json.loads(text)
    assert "cannot prevent it" in body["additional_context"]


def test_installed_gates_ask_to_fail_closed():
    """Cursor fails open by default; a crashed gate would silently permit what it guards."""
    config = A.adapters.get("cursor").hook_config([A.PRE_TOOL, A.FILE_CHANGED], "handler.py")
    assert config["hooks"]["preToolUse"][0]["failClosed"] is True
    # afterFileEdit decides nothing, so there is nothing to fail closed about.
    assert "failClosed" not in config["hooks"]["afterFileEdit"][0]


def test_pre_tool_installs_the_generic_gate_not_just_the_shell_one():
    config = A.adapters.get("cursor").hook_config([A.PRE_TOOL], "handler.py")
    assert "preToolUse" in config["hooks"]
