"""Mistral Vibe adapter: payloads as docs.mistral.ai/vibe/code/cli/hooks documents them (read 2026-10-11).

Tool names and inputs come from the mistral-vibe 2.26.1 sdist (vibe/core/tools/builtins).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402

BASE = {"session_id": "s1", "parent_session_id": None, "transcript_path": "/repo/s.jsonl", "cwd": "/repo"}
PRE_BASH = dict(
    BASE, hook_event_name="pre_tool", tool_name="bash", tool_call_id="c1", tool_input={"command": "rm -rf /"}
)
PRE_WRITE = dict(PRE_BASH, tool_name="write_file", tool_input={"file_path": "/repo/AGENTS.md", "content": "SECRET"})
POST_TOOL = dict(
    PRE_BASH, hook_event_name="post_tool", tool_status="success", tool_output={}, tool_output_text="ok", duration_ms=5
)
POST_AGENT = dict(BASE, hook_event_name="post_agent")


def _speak(raw, decision):
    return A.handle(raw, lambda e: decision, agent="mistral_vibe")


def test_the_snake_case_hook_type_alone_identifies_vibe():
    for raw in (PRE_BASH, PRE_WRITE, POST_TOOL, POST_AGENT):
        assert A.adapters.detect(raw) == "mistral_vibe"
    assert not A.adapters.get("mistral_vibe").claims(dict(PRE_BASH, hook_event_name="PreToolUse"))


def test_vibe_tool_inputs_parse_into_the_event():
    mod = A.adapters.get("mistral_vibe")
    shell = mod.parse(PRE_BASH)
    assert (shell.event, shell.command, shell.tool_use_id, shell.cwd) == (A.PRE_TOOL, "rm -rf /", "c1", "/repo")
    assert shell.tool in mod.SHELL_TOOLS
    write = mod.parse(PRE_WRITE)
    assert (write.path, write.content, write.tool in mod.WRITE_TOOLS) == ("/repo/AGENTS.md", "SECRET", True)
    edit = mod.parse(
        dict(PRE_WRITE, tool_name="edit", tool_input={"file_path": "a", "old_string": "x", "new_string": "y"})
    )
    assert edit.content == "y"
    assert mod.parse(POST_TOOL).output == "ok"
    assert mod.parse(POST_AGENT).event == A.STOP


@pytest.mark.parametrize("raw", [PRE_BASH, POST_AGENT], ids=["pre_tool", "post_agent"])
def test_a_deny_is_the_documented_decision_body(raw):
    text, code, _e, _d = _speak(raw, Decision.deny("rm -rf is blocked"))
    assert (json.loads(text), code) == ({"decision": "deny", "reason": "rm -rf is blocked"}, 0)


def test_an_allow_is_the_documented_passthrough():
    assert _speak(PRE_BASH, Decision.allow())[:2] == ("", 0)


def test_a_deny_at_post_tool_is_not_spoken():
    """Vibe's post_tool deny only rewrites the output text; it is not a gate."""
    assert _speak(POST_TOOL, Decision.deny("too late"))[:2] == ("", 0)


@pytest.mark.parametrize(
    "decision",
    [lambda: Decision.escalate("confirm?"), lambda: Decision.transform({"command": "ls"}, "narrow")],
    ids=["escalate", "transform"],
)
def test_what_agentseam_cannot_say_to_vibe_degrades_to_a_deny(decision):
    body = json.loads(_speak(PRE_BASH, decision())[0])
    assert body["decision"] == "deny"
    assert "hook_specific_output" not in body


def test_install_writes_the_hooks_toml_vibe_reads():
    """[[hooks]] tables keyed name/type/match/command, as Vibe's HookConfig validates them."""
    tomllib = pytest.importorskip("tomllib")
    mod = A.adapters.get("mistral_vibe")
    assert (mod.CONFIG_PATH, mod.CONFIG_FORMAT) == (".vibe/hooks.toml", "toml")
    text = mod.render_config(mod.hook_config([A.PRE_TOOL, A.STOP], "guard.py"))
    hooks = tomllib.loads(text)["hooks"]
    assert [h["type"] for h in hooks] == ["pre_tool", "post_agent"]
    assert all(set(h) <= {"name", "type", "match", "command"} and h["command"] == "guard.py" for h in hooks)
    assert hooks[0]["match"] == "*" and "match" not in hooks[1]
    assert len({h["name"] for h in hooks}) == len(hooks)
    narrowed = tomllib.loads(mod.render_config(mod.hook_config([A.PRE_TOOL], "guard.py", matcher="bash")))
    assert narrowed["hooks"][0]["match"] == "bash"


def test_two_commands_never_share_a_rule_name():
    """Vibe drops a second [[hooks]] table whose name it has already seen, in any file."""
    mod = A.adapters.get("mistral_vibe")
    one, two = (mod.hook_config([A.PRE_TOOL], cmd)[0]["name"] for cmd in ("a.py", "b.py"))
    assert one != two and one.startswith("agentseam-pre_tool-")


def test_the_grade_is_capped_by_docs_basis_and_fails_open():
    for event in (A.PRE_TOOL, A.STOP):
        assert A.enforcement_level("mistral_vibe", event) == "best-effort"
    assert A.enforcement_level("mistral_vibe", A.POST_TOOL) == "detect"
    assert A.enforcement_level("mistral_vibe", A.PROMPT_SUBMIT) == "none"
    assert A.adapters.get("mistral_vibe").NEEDS_TRUST
