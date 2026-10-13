"""OpenHands adapter: payloads as docs.openhands.dev's hooks page documents them (read 2026-10-11)."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402

#: The hooks page's own stdin example, with its command swapped for a harmless one.
PRE_SHELL = {
    "event_type": "PreToolUse",
    "tool_name": "terminal",
    "tool_input": {"command": "rg TODO"},
    "session_id": "abc-123",
    "working_dir": "/workspace",
}
#: file_editor's action fields, from the SDK's file_editor/definition.py at v1.54.0.
PRE_WRITE = dict(
    PRE_SHELL,
    tool_name="file_editor",
    tool_input={"command": "create", "path": "/workspace/AGENTS.md", "file_text": "SECRET=EXAMPLE-PLACEHOLDER"},
)
PROMPT = {"event_type": "UserPromptSubmit", "session_id": "abc-123", "working_dir": "/workspace", "message": "hi"}
STOP = {"event_type": "Stop", "session_id": "abc-123", "working_dir": "/workspace"}
POST_TOOL = dict(PRE_SHELL, event_type="PostToolUse", tool_response={"exit_code": 0})


def _speak(raw, decision):
    return A.handle(raw, lambda e: decision, agent="openhands")


def test_the_event_key_alone_identifies_openhands():
    """No other adapter reads `event_type`; renaming it to Claude's key must lose the claim."""
    for raw in (PRE_SHELL, PRE_WRITE, PROMPT, STOP, POST_TOOL):
        assert A.adapters.detect(raw) == "openhands"
    renamed = {("hook_event_name" if k == "event_type" else k): v for k, v in PRE_SHELL.items()}
    assert not A.adapters.get("openhands").claims(renamed)


def test_the_documented_fields_reach_the_event():
    mod = A.adapters.get("openhands")
    shell = mod.parse(PRE_SHELL)
    assert (shell.event, shell.tool, shell.command, shell.cwd) == (A.PRE_TOOL, "terminal", "rg TODO", "/workspace")
    assert shell.tool in mod.SHELL_TOOLS
    write = mod.parse(PRE_WRITE)
    assert (write.path, write.content) == ("/workspace/AGENTS.md", "SECRET=EXAMPLE-PLACEHOLDER")
    assert write.tool in mod.WRITE_TOOLS
    assert mod.parse(PROMPT).prompt == "hi"


def test_a_str_replace_carries_its_new_text_as_content():
    raw = dict(PRE_WRITE, tool_input={"command": "str_replace", "path": "a.py", "old_str": "x", "new_str": "y"})
    assert A.adapters.get("openhands").parse(raw).content == "y"


def test_a_deny_is_the_documented_decision_body():
    text, code, _e, _d = _speak(PRE_SHELL, Decision.deny("not here"))
    assert json.loads(text) == {"decision": "deny", "reason": "not here"}
    assert code == 0


def test_an_allow_is_silence():
    assert _speak(PRE_SHELL, Decision.allow())[:2] == ("", 0)


@pytest.mark.parametrize(
    "decision",
    [lambda: Decision.ask("confirm?"), lambda: Decision.transform({"command": "ls"}, "narrow")],
    ids=["escalate", "transform"],
)
def test_what_openhands_cannot_do_degrades_to_a_block_never_a_pass(decision):
    body = json.loads(_speak(PRE_SHELL, decision())[0])
    assert body["decision"] == "deny" and "OpenHands cannot" in body["reason"]


@pytest.mark.parametrize("raw", [PROMPT, STOP], ids=["prompt_submit", "stop"])
def test_prompt_submit_and_stop_can_block(raw):
    assert json.loads(_speak(raw, Decision.deny("no"))[0]) == {"decision": "deny", "reason": "no"}


def test_a_block_where_openhands_ignores_one_is_not_spoken():
    assert _speak(POST_TOOL, Decision.deny("too late"))[:2] == ("", 0)


def test_install_writes_the_claude_shaped_file_openhands_accepts():
    mod = A.adapters.get("openhands")
    assert mod.CONFIG_PATH == ".openhands/hooks.json"
    config = mod.hook_config([A.PRE_TOOL, A.STOP], "guard.py", matcher="terminal")
    assert config["hooks"]["PreToolUse"] == [
        {"matcher": "terminal", "hooks": [{"type": "command", "command": "guard.py"}]}
    ]
    assert "matcher" not in config["hooks"]["Stop"][0]


def test_the_grade_is_capped_by_docs_basis_and_fails_open():
    assert A.MATRIX["openhands"]["events"][A.PRE_TOOL]["fail_mode"] == "open"
    for event in (A.PRE_TOOL, A.PROMPT_SUBMIT, A.STOP):
        assert A.enforcement_level("openhands", event) == "best-effort"
    assert A.enforcement_level("openhands", A.POST_TOOL) == "detect"
    assert not A.can_rewrite("openhands", A.PRE_TOOL)
