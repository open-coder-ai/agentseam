"""goose adapter: payloads as goose-docs.ai's hooks guide documents them (read 2026-10-11)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402

#: The guide's own tool-event example, with its working_dir swapped for a neutral path.
POST_TOOL = {
    "event": "PostToolUse",
    "session_id": "abc-123",
    "matcher_context": "shell",
    "tool_name": "shell",
    "tool_input": {"command": "rg TODO"},
    "working_dir": "/repo",
}
PRE_WRITE = {
    "event": "PreToolUse",
    "session_id": "abc-123",
    "matcher_context": "write",
    "tool_name": "write",
    "tool_input": {"path": "AGENTS.md", "content": "AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY"},
    "working_dir": "/repo",
    "tool_call_id": "call-1",
}
PROMPT = {
    "event": "UserPromptSubmit",
    "session_id": "abc-123",
    "matcher_context": "summarize this file",
    "message": "summarize this file",
}
STOP = {"event": "Stop", "session_id": "abc-123", "last_assistant_message": "Done. I updated the file."}


def _speak(raw, decision):
    text, code, event, final = A.handle(raw, lambda e: decision, agent="goose")
    return text, code, event, final


def test_the_event_key_alone_identifies_goose():
    """No other adapter reads `event`; renaming it to Claude's key must lose the claim."""
    for raw in (POST_TOOL, PRE_WRITE, PROMPT, STOP):
        assert A.adapters.detect(raw) == "goose"
    renamed = {("hook_event_name" if k == "event" else k): v for k, v in PRE_WRITE.items()}
    assert not A.adapters.get("goose").claims(renamed)


def test_the_documented_fields_reach_the_event():
    event = A.adapters.get("goose").parse(PRE_WRITE)
    assert event.event == A.PRE_TOOL
    assert (event.tool, event.path, event.cwd, event.tool_use_id) == ("write", "AGENTS.md", "/repo", "call-1")
    assert "AWS_SECRET_ACCESS_KEY" in event.content
    shell = A.adapters.get("goose").parse(POST_TOOL)
    assert (shell.event, shell.command) == (A.POST_TOOL, "rg TODO")
    assert A.adapters.get("goose").parse(PROMPT).prompt == "summarize this file"


def test_an_edit_carries_its_new_text_as_content():
    """The developer `edit` tool's keys are path, before, after; `after` is what gets written."""
    raw = dict(PRE_WRITE, tool_name="edit", tool_input={"path": "AGENTS.md", "before": "x", "after": "SECRET=1"})
    event = A.adapters.get("goose").parse(raw)
    assert event.content == "SECRET=1"
    assert event.tool in A.adapters.get("goose").WRITE_TOOLS


def test_a_deny_is_the_documented_block_body():
    text, code, _e, _d = _speak(PRE_WRITE, Decision.deny("secret detected"))
    assert json.loads(text) == {"decision": "block", "reason": "secret detected"}
    assert code == 0


def test_an_allow_is_silence():
    """Exit 0 with empty stdout allows; anything else on stdout reads as no decision."""
    assert _speak(PRE_WRITE, Decision.allow())[:2] == ("", 0)


@pytest.mark.parametrize(
    "decision",
    [lambda: Decision.ask("confirm?"), lambda: Decision.transform({"content": "safe"}, "redact")],
    ids=["escalate", "transform"],
)
def test_what_goose_cannot_do_degrades_to_a_block_never_a_pass(decision):
    text, code, _e, _d = _speak(PRE_WRITE, decision())
    body = json.loads(text)
    assert body["decision"] == "block" and "goose cannot" in body["reason"]
    assert code == 0


def test_stop_can_block_and_keep_the_turn_going():
    body = json.loads(_speak(STOP, Decision.deny("tests still failing"))[0])
    assert body == {"decision": "block", "reason": "tests still failing"}


@pytest.mark.parametrize("raw", [POST_TOOL, PROMPT], ids=["post_tool", "prompt_submit"])
def test_a_block_where_goose_ignores_one_is_not_spoken(raw):
    assert _speak(raw, Decision.deny("too late"))[:2] == ("", 0)


@pytest.mark.parametrize("name", ["PreToolUseResult", "BeforeReadFile", "BeforeShellExecution", "AfterShellExecution"])
def test_observation_only_events_are_claimed_but_unknown(name):
    raw = dict(PRE_WRITE, event=name)
    assert A.adapters.detect(raw) == "goose"
    assert A.adapters.get("goose").parse(raw).event == A.UNKNOWN


def test_install_writes_a_hook_only_plugin_that_fails_closed_at_pre_tool():
    mod = A.adapters.get("goose")
    assert mod.CONFIG_PATH == ".agents/plugins/agentseam/hooks/hooks.json"
    config = mod.hook_config([A.PRE_TOOL, A.STOP], "guard.py", matcher="^shell$")
    rule = config["hooks"]["PreToolUse"][0]
    assert rule["matcher"] == "^shell$"
    assert rule["hooks"] == [{"type": "command", "command": "guard.py", "on_failure": "block"}]
    assert "matcher" not in config["hooks"]["Stop"][0]


def test_the_grade_is_capped_by_docs_basis():
    """on_failure: block makes PreToolUse fail closed, but a docs read cannot back more than best-effort."""
    assert A.MATRIX["goose"]["events"][A.PRE_TOOL]["fail_mode"] == "configurable"
    assert A.enforcement_level("goose", A.PRE_TOOL) == "best-effort"
    assert A.enforcement_level("goose", A.STOP) == "best-effort"
    assert A.enforcement_level("goose", A.POST_TOOL) == "detect"
    assert not A.can_rewrite("goose", A.PRE_TOOL)
