"""Factory Droid adapter: payloads as docs.factory.com/harness/hooks documents them (read 2026-10-11).

Tool inputs beyond the page's own Create example come from droid 0.238.0's shipped bundle.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402

DROID_MODES = ("off", "spec", "auto-low", "auto-medium", "auto-high")

#: The hooks page's tool-hook example, home paths set to /repo for the private-data gate.
PRE_CREATE = {
    "session_id": "abc123",
    "transcript_path": "/repo/.factory/projects/repo/session.jsonl",
    "cwd": "/repo",
    "permission_mode": "off",
    "hook_event_name": "PreToolUse",
    "tool_name": "Create",
    "tool_input": {"file_path": "/repo/file.txt", "content": "file content"},
}
PRE_EXECUTE = dict(PRE_CREATE, tool_name="Execute", tool_input={"command": "git push", "summary": "push"})
PROMPT = dict(
    {k: v for k, v in PRE_CREATE.items() if not k.startswith("tool")},
    hook_event_name="UserPromptSubmit",
    prompt="hi",
    has_images=False,
)
STOP = dict(PROMPT, hook_event_name="Stop", stop_hook_active=False, tool_execution_count=3, elapsed_time=10)
SESSION_START = dict(PROMPT, hook_event_name="SessionStart", source="startup")
POST_TOOL = dict(PRE_EXECUTE, hook_event_name="PostToolUse", tool_response={"exit_code": 0})


def _speak(raw, decision):
    return A.handle(raw, lambda e: decision, agent="factory_droid")


@pytest.mark.parametrize("mode", DROID_MODES)
@pytest.mark.parametrize(
    "raw", [PRE_CREATE, PROMPT, STOP, SESSION_START, POST_TOOL], ids=lambda r: r["hook_event_name"]
)
def test_every_droid_permission_mode_detects_as_factory_droid(raw, mode):
    """permission_mode rides on every Droid event; each of its five values is Droid's alone."""
    assert A.adapters.detect(dict(raw, permission_mode=mode)) == "factory_droid"


@pytest.mark.parametrize("mode", ["default", "plan", "acceptEdits", "bypassPermissions", None])
def test_a_claude_code_permission_mode_is_never_droids(mode):
    """The same envelope with a Claude Code value (or none) stays Claude Code's: no ambiguity."""
    raw = (
        dict(PRE_CREATE, permission_mode=mode)
        if mode
        else {k: v for k, v in PRE_CREATE.items() if k != "permission_mode"}
    )
    assert not A.adapters.get("factory_droid").claims(raw)
    assert A.adapters.detect(raw) == "claude_code"


def test_droid_tool_inputs_parse_into_the_event():
    mod = A.adapters.get("factory_droid")
    create = mod.parse(PRE_CREATE)
    assert (create.event, create.tool, create.path, create.content) == (
        A.PRE_TOOL,
        "Create",
        "/repo/file.txt",
        "file content",
    )
    assert create.tool in mod.WRITE_TOOLS
    shell = mod.parse(PRE_EXECUTE)
    assert (shell.command, shell.cwd) == ("git push", "/repo")
    assert shell.tool in mod.SHELL_TOOLS
    edit = mod.parse(
        dict(PRE_CREATE, tool_name="Edit", tool_input={"file_path": "a.py", "old_str": "x", "new_str": "y"})
    )
    assert (edit.path, edit.content) == ("a.py", "y")
    multi = {"file_path": "a.py", "changes": [{"old_str": "x", "new_str": "y"}, {"old_str": "p", "new_str": "q"}]}
    assert mod.parse(dict(PRE_CREATE, tool_name="MultiEdit", tool_input=multi)).content == "y\nq"
    patch = mod.parse(dict(PRE_CREATE, tool_name="ApplyPatch", tool_input={"input": "*** Begin Patch"}))
    assert (patch.tool in mod.WRITE_TOOLS, patch.content) == (True, "*** Begin Patch")
    assert mod.parse(PROMPT).prompt == "hi"
    assert mod.parse(POST_TOOL).output == json.dumps({"exit_code": 0})


def test_a_deny_at_pre_tool_is_the_documented_permission_decision():
    text, code, _e, _d = _speak(PRE_EXECUTE, Decision.deny("not here"))
    out = json.loads(text)["hookSpecificOutput"]
    assert (out["permissionDecision"], out["permissionDecisionReason"], code) == ("deny", "not here", 0)


@pytest.mark.parametrize("raw", [PROMPT, STOP], ids=["prompt_submit", "stop"])
def test_prompt_submit_and_stop_block_with_decision_block(raw):
    assert json.loads(_speak(raw, Decision.deny("no"))[0]) == {"decision": "block", "reason": "no"}


def test_an_allow_is_silence_never_an_auto_approve():
    """permissionDecision allow bypasses Droid's own prompt, so a plain allow never says it."""
    assert _speak(PRE_EXECUTE, Decision.allow())[:2] == ("", 0)


@pytest.mark.parametrize(
    "decision",
    [lambda: Decision.escalate("confirm?"), lambda: Decision.transform({"command": "ls"}, "narrow")],
    ids=["escalate", "transform"],
)
def test_ask_and_updated_input_degrade_to_a_deny_never_a_pass(decision):
    """Droid's ask falls through to its autonomy level, and updatedInput is merged, not replaced."""
    out = json.loads(_speak(PRE_EXECUTE, decision())[0])["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert "updatedInput" not in out


def test_install_writes_the_unwrapped_event_map_droid_reads():
    mod = A.adapters.get("factory_droid")
    assert mod.CONFIG_PATH == ".factory/hooks.json"
    config = mod.hook_config([A.PRE_TOOL, A.STOP], "guard.py", matcher="Execute")
    assert config["PreToolUse"] == [{"matcher": "Execute", "hooks": [{"type": "command", "command": "guard.py"}]}]
    assert "hooks" not in config and "matcher" not in config["Stop"][0]


def test_the_grade_is_capped_by_docs_basis_and_fails_open():
    for event in (A.PRE_TOOL, A.PROMPT_SUBMIT, A.STOP):
        assert A.enforcement_level("factory_droid", event) == "best-effort"
    assert A.enforcement_level("factory_droid", A.POST_TOOL) == "detect"
    assert not A.can_rewrite("factory_droid", A.PRE_TOOL)


@pytest.mark.parametrize(
    "raw",
    [
        {"hook_event_name": "PreToolUse", "cwd": "/repo", "session_id": "k1", "tool_name": "shell", "tool_input": {}},
        {"hook_event_name": "UserPromptSubmit", "cwd": "/repo", "session_id": "k1", "prompt": "hi"},
        {"hook_event_name": "Stop", "cwd": "/repo", "session_id": "k1"},
    ],
    ids=["kiro_v3_shell", "kiro_prompt", "kiro_stop"],
)
def test_kiro_payloads_that_d1_cannot_separate_are_still_not_droids(raw):
    """No permission_mode, so not Droid's; they stay where D1 left them (kiro row notes)."""
    assert A.adapters.detect(raw) == "claude_code"
