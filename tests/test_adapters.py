"""Contract tests: real vendor payload shapes in, correct dialect out.

Fixtures are the shapes we verified against primary sources — Claude Code live
(2.1.245), Cursor's own hook-example repo, and microsoft/vscode source for Copilot.
If a vendor changes its wire format, these fail loudly rather than a policy silently
never firing.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agentseam as A
from agentseam import Decision


def allow_all(_e):
    return Decision.allow()


def deny_all(e):
    return Decision.deny("test-deny")


# --------------------------------------------------------------- claude code
CC_WRITE = {
    "hook_event_name": "PreToolUse",
    "tool_name": "Write",
    "session_id": "s1",
    "tool_use_id": "t1",
    "cwd": "/repo",
    "tool_input": {"file_path": "CLAUDE.md", "content": "team uses pnpm"},
}
CC_EDIT = {
    "hook_event_name": "PreToolUse",
    "tool_name": "Edit",
    "session_id": "s1",
    "tool_input": {"file_path": "MEMORY.md", "new_string": "fact"},
}
CC_MULTI = {
    "hook_event_name": "PreToolUse",
    "tool_name": "MultiEdit",
    "tool_input": {"file_path": "a.md", "edits": [{"new_string": "one"}, {"new_string": "two"}]},
}
CC_BASH = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}
CC_POST = {"hook_event_name": "PostToolUse", "tool_name": "WebFetch", "tool_use_id": "w1", "tool_output": "page text"}


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


# -------------------------------------------------------------------- cursor
CU_SHELL = {"command": "echo x >> CLAUDE.md", "cwd": "/repo"}
CU_EDIT = {"file_path": ".cursor/rules/style.md", "edits": [{"new_string": "use named exports"}]}


def test_cursor_shell_blocks_pre_execution():
    text, code, event, _ = A.handle(CU_SHELL, deny_all)
    assert json.loads(text)["permission"] == "deny"
    assert event.event == A.PRE_TOOL and code == 0


def test_cursor_file_edit_is_detect_only():
    """Cursor has no beforeFileEdit: a deny must surface as post-write detection."""
    text, code, event, _ = A.handle(CU_EDIT, deny_all)
    assert event.event == A.POST_TOOL
    assert code == 2  # flagged, not blocked
    assert "cannot block" in json.loads(text)["user_message"]


def test_cursor_clean_edit_is_silent():
    text, code, _, _ = A.handle(CU_EDIT, allow_all)
    assert (text, code) == ("", 0)


# ------------------------------------------------------------ vscode copilot
VS_MEM_CREATE = {
    "tool_name": "memory",
    "session_id": "v1",
    "tool_input": {"command": "create", "path": "/memories/repo/p.md", "file_text": "pref"},
}
VS_MEM_REPLACE = {
    "tool_name": "copilot_memory",
    "tool_input": {"command": "str_replace", "path": "/memories/a.md", "old_str": "a", "new_str": "b"},
}
VS_MEM_VIEW = {"tool_name": "memory", "tool_input": {"command": "view", "path": "/memories/a.md"}}


def test_vscode_memory_tool_shapes():
    mod = A.adapters.get("vscode_copilot")
    assert mod.parse(VS_MEM_CREATE).content == "pref"
    assert mod.parse(VS_MEM_REPLACE).content == "b"
    assert mod.is_memory_write(mod.parse(VS_MEM_CREATE)) is True
    assert mod.is_memory_write(mod.parse(VS_MEM_VIEW)) is False  # view writes nothing


def test_vscode_speaks_claude_contract():
    text, _, _, _ = A.handle(VS_MEM_CREATE, deny_all)
    assert json.loads(text)["hookSpecificOutput"]["permissionDecision"] == "deny"


# ------------------------------------------------------------------ dispatch
def test_detect_never_guesses_between_agents():
    for raw in (CC_WRITE, CU_SHELL, CU_EDIT, VS_MEM_CREATE):
        assert A.adapters.detect(raw) is not None


def test_unknown_payload_allows_silently():
    text, code, event, decision = A.handle({"totally": "unknown"}, deny_all)
    assert (text, code, event) == ("", 0, None) and decision.outcome == A.ALLOW


def test_one_handler_runs_on_every_agent():
    """The core promise: identical handler, correct dialect everywhere."""

    def handler(e):
        return Decision.deny("secret") if "SECRET" in (e.content or "") else Decision.allow()

    outcomes = {}
    for raw in (CC_WRITE, VS_MEM_CREATE, CU_EDIT):
        poisoned = json.loads(json.dumps(raw))
        for holder in (poisoned.get("tool_input", {}), poisoned):
            for k in ("content", "file_text", "new_string"):
                if k in holder:
                    holder[k] = "SECRET"
        if "edits" in poisoned:
            poisoned["edits"] = [{"new_string": "SECRET"}]
        _t, _c, event, decision = A.handle(poisoned, handler)
        outcomes[event.agent] = decision.outcome
    assert outcomes == {"claude_code": "deny", "vscode_copilot": "deny", "cursor": "deny"}


# --------------------------------------------------------------- gemini cli
# Payload shapes from the vendor's own hooks reference (docs/hooks/reference.md).
GM_WRITE = {
    "hook_event_name": "BeforeTool",
    "tool_name": "write_file",
    "session_id": "g1",
    "cwd": "/repo",
    "tool_input": {"file_path": "GEMINI.md", "content": "team prefers pnpm"},
}
GM_REPLACE = {
    "hook_event_name": "BeforeTool",
    "tool_name": "replace",
    "tool_input": {"file_path": "GEMINI.md", "new_string": "updated fact"},
}
GM_SHELL = {
    "hook_event_name": "BeforeTool",
    "tool_name": "run_shell_command",
    "tool_input": {"command": "rm -rf /"},
}
GM_AFTER = {"hook_event_name": "AfterTool", "tool_name": "write_file", "tool_output": "ok"}


def test_gemini_parses_its_own_tool_names():
    mod = A.adapters.get("gemini_cli")
    assert mod.parse(GM_WRITE).content == "team prefers pnpm"
    assert mod.parse(GM_REPLACE).content == "updated fact"
    assert mod.parse(GM_SHELL).command == "rm -rf /"
    assert mod.parse(GM_AFTER).event == A.POST_TOOL


def test_gemini_deny_is_top_level_not_nested():
    """Gemini puts decision at the top level; nesting it Claude-style would no-op."""
    text, code, _, _ = A.handle(GM_WRITE, deny_all)
    payload = json.loads(text)
    assert payload["decision"] == "deny"
    assert payload["reason"] == "test-deny"
    assert "hookSpecificOutput" not in payload
    assert code == 0


def test_gemini_rewrite_uses_hook_specific_tool_input():
    text, _, _, _ = A.handle(GM_WRITE, lambda e: Decision.rewrite({"content": "redacted"}))
    assert json.loads(text)["hookSpecificOutput"]["tool_input"] == {"content": "redacted"}


def test_gemini_ask_degrades_to_deny_with_explanation():
    """No interactive confirmation exists in this protocol; never silently allow."""
    text, _, _, _ = A.handle(GM_WRITE, lambda e: Decision.ask("needs a human"))
    payload = json.loads(text)
    assert payload["decision"] == "deny"
    assert "confirmation required" in payload["reason"]


def test_gemini_allow():
    assert json.loads(A.handle(GM_WRITE, allow_all)[0])["decision"] == "allow"


def test_one_handler_covers_gemini_too():
    def handler(e):
        return Decision.deny("secret") if "SECRET" in (e.content or "") else Decision.allow()

    poisoned = json.loads(json.dumps(GM_WRITE))
    poisoned["tool_input"]["content"] = "SECRET"
    _t, _c, event, decision = A.handle(poisoned, handler)
    assert event.agent == "gemini_cli" and decision.outcome == "deny"
