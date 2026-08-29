"""Instruction files: reach every agent without clobbering anything a human wrote."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest  # noqa: E402

from agentseam import instructions as I  # noqa: E402


def test_every_agent_has_at_least_one_file():
    for agent in I.agents():
        assert I.paths(agent), agent


def test_plan_prefers_the_shared_file_over_copies():
    """Fourteen near-identical files is the disease; one shared file is the cure."""
    decided = I.plan()
    assert decided["shared"] == "AGENTS.md"
    assert len(decided["covered"]) >= 7
    # Nobody covered by AGENTS.md gets a second file of their own to drift.
    assert not set(decided["covered"]) & set(decided["per_agent"])
    assert len(decided["per_agent"]) < len(I.agents())


def test_claude_code_gets_its_own_file_and_a_pointer():
    """Claude Code does not read AGENTS.md natively, so it needs CLAUDE.md."""
    decided = I.plan(["claude_code"])
    assert decided["per_agent"]["claude_code"] == "CLAUDE.md"
    assert decided["shared"] is None  # nothing in this selection reads the shared file


def test_plan_rejects_unknown_agents():
    with pytest.raises(KeyError):
        I.plan(["not_an_agent"])


def test_write_creates_then_updates_in_place(tmp_path):
    first = I.write("use pnpm", ["codex_cli"], str(tmp_path))
    assert first == {"AGENTS.md": "created"}
    assert "use pnpm" in (tmp_path / "AGENTS.md").read_text()

    second = I.write("use pnpm", ["codex_cli"], str(tmp_path))
    assert second == {"AGENTS.md": "unchanged"}

    third = I.write("use bun", ["codex_cli"], str(tmp_path))
    assert third == {"AGENTS.md": "updated"}
    text = (tmp_path / "AGENTS.md").read_text()
    assert "use bun" in text and "use pnpm" not in text


def test_human_content_is_never_clobbered(tmp_path):
    """The whole contract. These files are mostly human-written."""
    target = tmp_path / "AGENTS.md"
    target.write_text("# House rules\n\nAlways run the linter.\n")

    I.write("prefer named exports", ["codex_cli"], str(tmp_path))
    text = target.read_text()
    assert "# House rules" in text and "Always run the linter." in text
    assert "prefer named exports" in text

    # A second, different write replaces only our block.
    I.write("prefer default exports", ["codex_cli"], str(tmp_path))
    text = target.read_text()
    assert "# House rules" in text and "Always run the linter." in text
    assert "prefer default exports" in text and "prefer named exports" not in text


def test_remove_strips_only_our_block(tmp_path):
    target = tmp_path / "AGENTS.md"
    target.write_text("# House rules\n\nAlways run the linter.\n")
    I.write("temporary note", ["codex_cli"], str(tmp_path))

    I.remove(["codex_cli"], str(tmp_path))
    text = target.read_text()
    assert "# House rules" in text and "Always run the linter." in text
    assert "temporary note" not in text
    assert I.BEGIN not in text and I.END not in text


def test_dry_run_writes_nothing(tmp_path):
    result = I.write("hello", ["codex_cli"], str(tmp_path), dry_run=True)
    assert result == {"AGENTS.md": "created"}
    assert not (tmp_path / "AGENTS.md").exists()


def test_write_reaches_every_agent_with_fewer_files_than_agents(tmp_path):
    result = I.write("one policy", None, str(tmp_path))
    assert len(result) < len(I.agents())
    assert "AGENTS.md" in result
    assert "CLAUDE.md" in result  # the one that cannot use the shared file


def test_discover_reports_what_exists(tmp_path):
    assert I.discover(str(tmp_path)) == {}
    I.write("x", ["codex_cli", "claude_code"], str(tmp_path))
    found = I.discover(str(tmp_path))
    assert "AGENTS.md" in found["codex_cli"]
    assert "CLAUDE.md" in found["claude_code"]


def test_nested_paths_are_created(tmp_path):
    I.write("rule", ["junie"], str(tmp_path))
    assert (tmp_path / ".junie" / "guidelines.md").exists()


def test_the_readme_arithmetic_cannot_drift():
    """README says "16 agents reached with 9 files written". Pin it to the data.

    The last claim ("14 agents with 7 files") went stale the day Tabnine landed and sat
    wrong until an audit counted. covered + per_agent must add up to every agent the map
    knows, and the files written are the shared one plus one per uncovered agent.

    It moved to 9 files on 2026-08-29 when aider's `shared` was corrected from True to
    False: aider reads only what .aider.conf.yml lists under `read:`, so claiming it picks
    up AGENTS.md natively had it counted as covered while it read nothing. It moved to 16
    agents the same day when `copilot` (the Agent Plugins 1.0 marketplace bundle identity;
    see packaging_data.PACKAGING) joined the matrix and was given the same instruction files
    as vscode_copilot -- a real repo running an installed copilot-format plugin is running
    actual GitHub Copilot, reading the exact same files. Covered, not per-agent, so the file
    count did not move with it.
    """
    p = I.plan(I.agents(), repo_root=".")
    agents_reached = len(p["covered"]) + len(p["per_agent"])
    files_written = (1 if p["shared"] else 0) + len(p["per_agent"])
    assert agents_reached == len(I.INSTRUCTION_FILES) == 16
    assert files_written == 9
