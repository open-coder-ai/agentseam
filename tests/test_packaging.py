"""Primitive 3 tests.

The load-bearing assertions are the ones about overlap: that a skill really is the same
file in two bundle formats, and that VS Code really does read another agent's folders. Get
either wrong and the module's main claim -- write it once -- stops being true.
"""

from __future__ import annotations

import json

import pytest

from agentseam import packaging
from agentseam.packaging import Bundle, Part
from agentseam.packaging_data import (
    ALSO_READS,
    COMMAND,
    HOOKS,
    MCP,
    PACKAGING,
    PART_LIMITS,
    PARTS,
    SKILL,
    SUBAGENT,
    UNRECORDED,
)


@pytest.fixture
def bundle():
    return Bundle(
        "secrets-guard",
        version="1.2.0",
        description="Keeps secrets out of memory files",
        parts=[
            Part(SKILL, "secret-scan", "# Secret scan\nRun this before writing."),
            Part(SUBAGENT, "auditor", "You audit diffs."),
            Part(COMMAND, "scan", "Scan {{args}} for secrets.", description="Scan a path"),
        ],
    )


def test_part_rejects_a_kind_it_does_not_know():
    with pytest.raises(ValueError):
        Part("plugin", "x", "y")


@pytest.mark.parametrize("agent", sorted(PACKAGING))
def test_every_agent_answers_for_every_part(agent):
    """None means "no equivalent" and is a claim; a missing key would just be a gap."""
    assert set(PACKAGING[agent]["parts"]) == set(PARTS)


@pytest.mark.parametrize("agent", sorted(PACKAGING))
def test_every_agent_records_how_it_was_verified(agent):
    verified = PACKAGING[agent]["verified"]
    assert verified["method"] and verified["date"]


def test_a_skill_is_literally_the_same_file_in_both_bundle_formats():
    """The claim the module is built on. If this drifts, "write it once" is a lie."""
    shared = packaging.same_path_for(SKILL)
    assert shared["skills/{name}/SKILL.md"] == ["claude_code", "gemini_cli"]
    assert packaging.same_path_for(SUBAGENT)["agents/{name}.md"] == ["claude_code", "gemini_cli"]
    assert packaging.same_path_for(HOOKS)["hooks/hooks.json"] == ["claude_code", "gemini_cli"]


def test_commands_are_the_part_that_never_carries_across():
    """Same folder in two formats, but .md against .toml -- so it is written twice."""
    grouped = packaging.same_path_for(COMMAND)
    assert all(len(names) == 1 for names in grouped.values())


def test_vscode_reads_another_agents_folders():
    """Committing .claude/skills ships skills to VS Code whether or not that was the intent."""
    assert ".claude/skills" in packaging.also_reads("vscode_copilot", SKILL)
    assert ".claude/settings.json" in packaging.also_reads("vscode_copilot", HOOKS)
    assert packaging.also_reads("claude_code") == {}


def test_plan_renders_a_claude_plugin(bundle):
    result = packaging.plan("claude_code", bundle)
    assert result.complete
    manifest = json.loads(result.files[".claude-plugin/plugin.json"])
    assert manifest == {
        "name": "secrets-guard",
        "version": "1.2.0",
        "description": "Keeps secrets out of memory files",
    }
    assert "skills/secret-scan/SKILL.md" in result.files
    assert result.files["commands/scan.md"] == "Scan {{args}} for secrets."


def test_plan_renders_a_gemini_extension_with_toml_commands(bundle):
    result = packaging.plan("gemini_cli", bundle)
    assert result.complete
    assert "gemini-extension.json" in result.files
    command = result.files["commands/scan.toml"]
    assert 'description = "Scan a path"' in command
    assert 'prompt = "Scan {{args}} for secrets."' in command
    assert result.root == ".gemini/extensions/secrets-guard"


def test_a_multiline_command_body_uses_the_triple_quoted_toml_form():
    body = 'Line one.\nLine two with a "quote".'
    result = packaging.plan("gemini_cli", Bundle("b", parts=[Part(COMMAND, "c", body)]))
    rendered = result.files["commands/c.toml"]
    assert rendered.startswith('prompt = """\n')
    assert 'Line two with a "quote".' in rendered


def test_vscode_gets_doubled_extensions_and_no_manifest(bundle):
    result = packaging.plan("vscode_copilot", bundle)
    assert result.complete
    assert ".github/agents/auditor.agent.md" in result.files
    assert ".github/prompts/scan.prompt.md" in result.files
    assert not any(name.endswith("plugin.json") or name.endswith("gemini-extension.json") for name in result.files)
    assert result.root == "."  # part paths are already repo-relative


def test_an_unsupported_part_is_reported_with_the_agents_own_reason():
    """A generic message would understate Gemini, which supports MCP -- just in the manifest."""
    result = packaging.plan("gemini_cli", Bundle("b", parts=[Part(MCP, "servers", "{}")]))
    assert not result.complete
    assert "gemini-extension.json" in result.unrepresentable[0].reason
    assert PART_LIMITS[("gemini_cli", MCP)] == result.unrepresentable[0].reason


def test_unrecorded_agents_raise_rather_than_returning_an_empty_layout(bundle):
    for agent in UNRECORDED:
        assert agent not in PACKAGING
        with pytest.raises(KeyError):
            packaging.plan(agent, bundle)


def test_codex_is_recorded_as_having_skills_we_could_not_locate():
    """ "No packaging" would be false: its approval config gates skill script execution."""
    assert "skills exist" in UNRECORDED["codex_cli"]


def test_every_packaging_agent_is_an_agent_the_matrix_knows():
    from agentseam.matrix import MATRIX

    assert set(PACKAGING) <= set(MATRIX)
    assert set(UNRECORDED) <= set(MATRIX)
    assert set(ALSO_READS) <= set(MATRIX)
