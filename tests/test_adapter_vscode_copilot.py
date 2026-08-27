"""VS Code Copilot adapter: the memory tool is the write surface."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import VS_MEM_CREATE, VS_MEM_REPLACE, VS_MEM_VIEW  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def allow_all(_e):
    return Decision.allow()


def deny_all(_e):
    return Decision.deny("test-deny")


def test_vscode_memory_tool_shapes():
    mod = A.adapters.get("vscode_copilot")
    assert mod.parse(VS_MEM_CREATE).content == "pref"
    assert mod.parse(VS_MEM_REPLACE).content == "b"
    assert mod.is_memory_write(mod.parse(VS_MEM_CREATE)) is True
    assert mod.is_memory_write(mod.parse(VS_MEM_VIEW)) is False  # view writes nothing


def test_vscode_speaks_claude_contract():
    text, _, _, _ = A.handle(VS_MEM_CREATE, deny_all)
    assert json.loads(text)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_the_user_prompt_reaches_a_prompt_policy():
    """userPromptSubmitted parsed to prompt_submit, but parse() never read the prompt text,
    so `event.prompt` was None and any prompt-based policy on this agent did nothing.
    Its envelope-twins claude_code and gemini_cli both read it."""
    ev = A.adapters.get("vscode_copilot").parse({"hookEventName": "userPromptSubmitted", "prompt": "delete prod"})
    assert ev.event == A.PROMPT_SUBMIT
    assert ev.prompt == "delete prod"
