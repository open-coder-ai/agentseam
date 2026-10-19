"""Cline adapter: payloads as .clinerules/hooks/README.md in cline/cline documents them (read 2026-10-11).

The CLI/SDK shape (hookName tool_call, a raw tool_call) is from sdk/packages/core/src/hooks/hook-file-hooks.ts
at the same commit; tool inputs from sdk/packages/core/src/extensions/tools/schemas.ts.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import pytest  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402
from agentseam import install as I  # noqa: E402
from agentseam.cli_report import trust_note  # noqa: E402

BASE = {"clineVersion": "4.1.23", "timestamp": "t", "taskId": "task-1", "workspaceRoots": ["/repo"], "userId": "u"}
PRE_WRITE = dict(
    BASE,
    hookName="PreToolUse",
    preToolUse={"toolName": "write_to_file", "parameters": {"path": "AGENTS.md", "content": "SECRET"}},
)
CLI_RUN = dict(
    BASE,
    clineVersion="",
    hookName="tool_call",
    agent_id="a1",
    parent_agent_id=None,
    iteration=1,
    tool_call={"id": "c1", "name": "run_commands", "input": {"commands": ["ls", "rm -rf /"]}},
    preToolUse={"toolName": "run_commands", "parameters": {"commands": '["ls", "rm -rf /"]'}},
)
POST_RUN = dict(
    BASE,
    hookName="PostToolUse",
    postToolUse={
        "toolName": "run_commands",
        "parameters": {"commands": '["npm test"]'},
        "result": "1 test failed",
        "success": False,
        "executionTimeMs": 5,
    },
)
PROMPT = dict(BASE, hookName="UserPromptSubmit", userPromptSubmit={"prompt": "hi", "attachments": []})
DETECT_ONLY = ("PostToolUse", "tool_result", "UserPromptSubmit", "prompt_submit", "TaskStart", "agent_start")


def _speak(raw, decision):
    return A.handle(raw, lambda e: decision, agent="cline")


def test_cline_version_beside_hook_name_identifies_cline_on_both_hosts():
    for raw in (PRE_WRITE, CLI_RUN, POST_RUN, PROMPT):
        assert A.adapters.detect(raw) == "cline"
    no_version = {k: v for k, v in PRE_WRITE.items() if k != "clineVersion"}
    assert not A.adapters.get("cline").claims(no_version)


def test_both_hosts_parse_to_the_same_tool_call():
    mod = A.adapters.get("cline")
    write = mod.parse(PRE_WRITE)
    assert (write.event, write.tool, write.path, write.content) == (A.PRE_TOOL, "write_to_file", "AGENTS.md", "SECRET")
    assert (write.session_id, write.cwd, write.tool in mod.WRITE_TOOLS) == ("task-1", "/repo", True)
    run = mod.parse(CLI_RUN)
    assert (run.event, run.command, run.tool_use_id, run.tool in mod.SHELL_TOOLS) == (
        A.PRE_TOOL,
        "ls\nrm -rf /",
        "c1",
        True,
    )
    vscode_run = dict(PRE_WRITE, preToolUse=CLI_RUN["preToolUse"])
    assert mod.parse(vscode_run).command == "ls\nrm -rf /"


@pytest.mark.parametrize(
    ("tool", "params", "field", "value"),
    [
        ("editor", {"path": "/repo/a.ts", "old_text": "x", "new_text": "y"}, "content", "y"),
        ("apply_patch", {"input": "*** Begin Patch"}, "content", "*** Begin Patch"),
        ("run_commands", {"commands": "npm test"}, "command", "npm test"),
        ("execute_command", {"command": "npm test"}, "command", "npm test"),
    ],
)
def test_each_documented_tool_input_reaches_the_event(tool, params, field, value):
    raw = dict(PRE_WRITE, preToolUse={"toolName": tool, "parameters": params})
    assert getattr(A.adapters.get("cline").parse(raw), field) == value


def test_post_tool_and_prompt_fields():
    mod = A.adapters.get("cline")
    post = mod.parse(POST_RUN)
    assert (post.event, post.output, post.command) == (A.POST_TOOL, "1 test failed", "npm test")
    assert (mod.parse(PROMPT).event, mod.parse(PROMPT).prompt) == (A.PROMPT_SUBMIT, "hi")


@pytest.mark.parametrize("raw", [PRE_WRITE, CLI_RUN], ids=["vscode", "cli"])
def test_a_deny_is_the_documented_cancel_object(raw):
    text, code, _e, _d = _speak(raw, Decision.deny("no secrets in AGENTS.md"))
    assert (json.loads(text), code) == ({"cancel": True, "errorMessage": "no secrets in AGENTS.md"}, 0)


@pytest.mark.parametrize("raw", [PRE_WRITE, CLI_RUN], ids=["vscode", "cli"])
def test_an_allow_is_the_documented_continue_and_carries_context(raw):
    text, code, _e, _d = _speak(raw, Decision.allow())
    assert (json.loads(text), code) == ({"cancel": False}, 0)
    text, _c, _e, _d = _speak(raw, Decision.allow(context="use .ts files"))
    assert json.loads(text) == {"cancel": False, "contextModification": "use .ts files"}


def test_escalate_and_transform_degrade_to_a_cancel_never_a_pass():
    for decision in (Decision.escalate("confirm"), Decision.transform({"path": "b"}, "redirect")):
        body = json.loads(_speak(PRE_WRITE, decision)[0])
        assert body["cancel"] is True
        assert "so this is a block" in body["errorMessage"]


@pytest.mark.parametrize("hook_name", DETECT_ONLY)
def test_detect_only_events_answer_nothing(hook_name):
    text, code, _e, _d = _speak(dict(PROMPT, hookName=hook_name), Decision.deny("policy"))
    assert (text, code) == ("", 0)


def test_install_writes_one_executable_per_event(tmp_path):
    path = I.install("cline", [A.PRE_TOOL, A.STOP], "guard --strict", repo_root=str(tmp_path))
    assert Path(path) == tmp_path / ".clinerules" / "hooks"
    assert sorted(p.name for p in Path(path).iterdir()) == ["PreToolUse", "TaskComplete"]
    text = (Path(path) / "PreToolUse").read_text(encoding="utf-8")
    assert text.splitlines()[0] == "#!/bin/sh"
    assert "\nguard --strict cline\n" in text
    if os.name != "nt":
        assert os.stat(Path(path) / "PreToolUse").st_mode & 0o111 == 0o111
    assert I.installed("cline", str(tmp_path))
    assert I.installed("cline", str(tmp_path), events=[A.PRE_TOOL], command="guard --strict")
    assert not I.installed("cline", str(tmp_path), events=[A.PRE_TOOL], command="other")
    I.install("cline", [A.PRE_TOOL], "guard --strict", repo_root=str(tmp_path))
    assert (Path(path) / "PreToolUse").read_text(encoding="utf-8") == text


def test_install_refuses_a_hook_file_it_did_not_write(tmp_path):
    hooks = tmp_path / ".clinerules" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "PreToolUse").write_text("#!/bin/sh\necho '{\"cancel\": false}'\n", encoding="utf-8")
    with pytest.raises(I.ConfigUnreadableError):
        I.install("cline", [A.PRE_TOOL, A.STOP], "guard", repo_root=str(tmp_path))
    assert sorted(p.name for p in hooks.iterdir()) == ["PreToolUse"]
    assert not I.installed("cline", str(tmp_path))


def test_uninstall_removes_only_what_it_wrote(tmp_path):
    hooks = tmp_path / ".clinerules" / "hooks"
    I.install("cline", [A.PRE_TOOL, A.PROMPT_SUBMIT], "guard", repo_root=str(tmp_path))
    with open(hooks / "UserPromptSubmit", "a", encoding="utf-8") as fh:
        fh.write("echo kept\n")
    assert I.uninstall("cline", str(tmp_path)) is True
    assert sorted(p.name for p in hooks.iterdir()) == ["UserPromptSubmit"]
    assert (hooks / "UserPromptSubmit").read_text(encoding="utf-8") == "#!/bin/sh\necho kept\n"
    assert I.uninstall("cline", str(tmp_path)) is False


def test_install_names_the_settings_switch():
    assert "Enable Hooks" in trust_note("cline")


@pytest.mark.skipif(os.name == "nt", reason="Cline hooks run on macOS and Linux only")
def test_the_installed_file_runs_and_answers_in_dialect(tmp_path):
    guard = tmp_path / "guard.py"
    guard.write_text(
        "import sys\nsys.path.insert(0, %r)\nimport agentseam as A\n"
        "sys.exit(A.run(lambda e: A.Decision.deny('blocked: ' + e.command), agent='cline'))\n" % str(ROOT / "src"),
        encoding="utf-8",
    )
    path = I.install("cline", [A.PRE_TOOL], '"%s" "%s"' % (sys.executable, guard), repo_root=str(tmp_path))
    done = subprocess.run(
        [str(Path(path) / "PreToolUse")], input=json.dumps(CLI_RUN), capture_output=True, text=True, check=False
    )
    assert done.returncode == 0, done.stderr
    assert json.loads(done.stdout) == {"cancel": True, "errorMessage": "blocked: ls\nrm -rf /"}


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
@pytest.mark.parametrize("owned", [True, False], ids=["link-to-owned", "link-to-foreign"])
def test_a_symlinked_hook_file_is_refused_and_its_target_left_alone(tmp_path, owned):
    elsewhere = tmp_path / "elsewhere"
    if owned:
        I.install("cline", [A.PRE_TOOL], "guard", repo_root=str(elsewhere))
        target = elsewhere / ".clinerules" / "hooks" / "PreToolUse"
    else:
        target = tmp_path / "target.sh"
        target.write_text("echo foreign\n", encoding="utf-8")
    before = (target.read_bytes(), os.stat(target).st_mode)
    hooks = tmp_path / "repo" / ".clinerules" / "hooks"
    hooks.mkdir(parents=True)
    (hooks / "PreToolUse").symlink_to(target)
    with pytest.raises(I.ConfigUnreadableError):
        I.install("cline", [A.PRE_TOOL], "guard", repo_root=str(tmp_path / "repo"))
    with pytest.raises(I.ConfigUnreadableError):
        I.uninstall("cline", str(tmp_path / "repo"))
    assert (target.read_bytes(), os.stat(target).st_mode) == before
