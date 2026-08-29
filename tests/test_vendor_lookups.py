"""The per-vendor answers a caller needs and can get nowhere else.

These three lookups exist because a policy engine building a hook command has to know things
that differ per product and are invisible when wrong:

  * which token reaches the plugin's own directory,
  * which tool name a shell command arrives under,
  * whether a `matcher` even means a tool name at this event.

Each has the same failure shape. Get it wrong and nothing raises: the command resolves to a
path that is not there, or the matcher matches nothing, and the install still reports success
while the guard never fires. That is why they are recorded rather than passed in by callers,
and why an unestablished answer is an empty one rather than a plausible guess.
"""

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
        # Codex sets PLUGIN_ROOT as its own name and CLAUDE_PLUGIN_ROOT beside it "for OOTB
        # compat with existing plugins that use this env var" (discovery.rs). Its own name is
        # preferred; both work.
        ("codex_cli", "${PLUGIN_ROOT}"),
        ("cursor", "${CURSOR_PLUGIN_ROOT}"),
        ("vscode_copilot", "${PLUGIN_ROOT}"),
        # Gemini's own spelling, established from docs/extensions/reference.md: substitution
        # is documented inside both gemini-extension.json and hooks/hooks.json.
        ("gemini_cli", "${extensionPath}"),
    ],
)
def test_the_preferred_plugin_root_token_per_format(agent, expected):
    assert plugin_root(agent) == expected


def test_an_unestablished_plugin_root_is_none_not_a_guess():
    """Windsurf's vendor docs were unreachable from this environment; no token is claimed."""
    assert plugin_root("windsurf") is None


def test_codex_plugin_root_the_trap_is_written_down():
    """`${CODEX_PLUGIN_ROOT}` appears in Codex's own TUI sample and is set nowhere.

    A hook command copied from that sample resolves to nothing and the guard never launches.
    It is exactly the plausible-looking wrong answer this lookup exists to prevent, so the
    module says so where someone reaching for it would look.
    """
    import agentseam.packaging_data as data

    source = Path(data.__file__).read_text()
    assert "${CODEX_PLUGIN_ROOT} is a trap" in source
    for tokens in (r["plugin_root"] for r in PACKAGING.values()):
        assert "${CODEX_PLUGIN_ROOT}" not in tokens


def test_shell_tools_are_recorded_only_where_established():
    """A sibling guardrail hardcodes "Bash" for four vendors. Two of those are unverified."""
    assert adapters.shell_tools("claude_code") == ("Bash",)
    assert adapters.shell_tools("gemini_cli") == ("run_shell_command",)
    for agent in ("cursor", "vscode_copilot", "windsurf"):
        assert adapters.shell_tools(agent) == (), "%s: () means not established, not no shell" % agent


def test_every_adapter_answers_the_shell_tool_question():
    for agent in sorted(adapters.ADAPTERS):
        assert isinstance(adapters.shell_tools(agent), tuple)


def test_cursor_writes_no_matcher_because_its_meaning_is_unestablished():
    """Under beforeShellExecution the matcher is a COMMAND-TEXT regex, not a tool name.

    A caller passing the reasonable "Bash" would match almost nothing and silently disable the
    gate. What preToolUse's matcher matches was not established, so none is written: no matcher
    gates every call, which over-gates rather than under-gates.
    """
    config = adapters.get("cursor").hook_config(["pre_tool"], "CMD", matcher="Bash")
    for entries in config["hooks"].values():
        for entry in entries:
            assert "matcher" not in entry


def test_adapters_that_do_take_a_tool_name_matcher_still_write_it():
    """The Cursor rule is about Cursor, not a blanket retreat from matchers."""
    config = adapters.get("claude_code").hook_config(["pre_tool"], "CMD", matcher="Bash")
    written = [e for entries in config["hooks"].values() for e in entries]
    assert any(e.get("matcher") == "Bash" for e in written)
