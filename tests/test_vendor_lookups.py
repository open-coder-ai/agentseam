"""The per-vendor answers a caller needs and can get nowhere else."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentseam import adapters  # noqa: E402
from agentseam.packaging import plugin_root  # noqa: E402
from agentseam.packaging_data import PACKAGING  # noqa: E402


def test_every_packaging_format_answers_the_plugin_root_question():
    """Including with an empty tuple, which is the answer "not established here"."""
    for agent, row in sorted(PACKAGING.items()):
        assert "plugin_root" in row, "%s must record a plugin-root token, even as ()" % agent
        assert isinstance(row["plugin_root"], tuple), agent


@pytest.mark.parametrize(
    "agent,expected",
    [
        ("claude_code", "${CLAUDE_PLUGIN_ROOT}"),
        ("codex_cli", "${PLUGIN_ROOT}"),
        ("cursor", "${CURSOR_PLUGIN_ROOT}"),
        ("vscode_copilot", "${PLUGIN_ROOT}"),
        ("gemini_cli", "${extensionPath}"),
    ],
)
def test_the_preferred_plugin_root_token_per_format(agent, expected):
    assert plugin_root(agent) == expected


def test_an_unestablished_plugin_root_is_none_not_a_guess():
    """Windsurf's vendor docs were unreachable from this environment; no token is claimed."""
    assert plugin_root("windsurf") is None


def test_codex_plugin_root_the_trap_is_written_down():
    """`${CODEX_PLUGIN_ROOT}` appears in Codex's own TUI sample and is set nowhere."""
    import agentseam.packaging_data as data

    source = Path(data.__file__).read_text()
    assert "${CODEX_PLUGIN_ROOT} is a trap" in source
    for tokens in (r["plugin_root"] for r in PACKAGING.values()):
        assert "${CODEX_PLUGIN_ROOT}" not in tokens


def test_shell_tools_are_recorded_only_where_established():
    """A sibling guardrail hardcodes "Bash" for four vendors; two were unverified until the
    post-C2 recount sourced them (recount/sourced.py holds the citations): Codex's live
    capture settled Bash, and Copilot's hooks reference names runtime bash/powershell with
    Bash as the Claude spelling PascalCase payloads report."""
    assert adapters.shell_tools("claude_code") == ("Bash",)
    assert adapters.shell_tools("gemini_cli") == ("run_shell_command",)
    assert adapters.shell_tools("codex_cli") == ("Bash",)
    assert adapters.shell_tools("vscode_copilot") == ("bash", "powershell", "Bash")
    for agent in ("cursor", "windsurf"):
        assert adapters.shell_tools(agent) == (), "%s: () means not established, not no shell" % agent


def test_every_adapter_answers_the_shell_tool_question():
    for agent in sorted(adapters.ADAPTERS):
        assert isinstance(adapters.shell_tools(agent), tuple)


def test_cursor_writes_no_matcher_because_its_meaning_is_unestablished():
    """Under beforeShellExecution the matcher is a COMMAND-TEXT regex, not a tool name."""
    config = adapters.get("cursor").hook_config(["pre_tool"], "CMD", matcher="Bash")
    for entries in config["hooks"].values():
        for entry in entries:
            assert "matcher" not in entry


def test_adapters_that_do_take_a_tool_name_matcher_still_write_it():
    """The Cursor rule is about Cursor, not a blanket retreat from matchers."""
    config = adapters.get("claude_code").hook_config(["pre_tool"], "CMD", matcher="Bash")
    written = [e for entries in config["hooks"].values() for e in entries]
    assert any(e.get("matcher") == "Bash" for e in written)
