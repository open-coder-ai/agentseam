"""Tests for the Copilot Agent Plugins 1.0 marketplace bundle (R2).

Fixture shape matches microsoft/vscode-docs' own example directory exactly: a
`test-runner` skill, a `test-reviewer` agent, and a hook script -- see
packaging_data.PACKAGING["copilot"]["verified"] for the source read.
"""

from __future__ import annotations

import json

import pytest

from agentseam import packaging
from agentseam.matrix_gaps import GAPS
from agentseam.packaging import Bundle, Part
from agentseam.packaging_data import COMMAND, EXECUTABLE, HOOKS, MCP, PACKAGING, PART_LIMITS, SKILL, SUBAGENT


@pytest.fixture
def bundle():
    return Bundle(
        "my-testing-plugin",
        version="1.2.0",
        description="React development utilities",
        parts=[
            Part(SKILL, "test-runner", "# Testing skill\nRun this before merging."),
            Part(SUBAGENT, "test-reviewer", "You review test diffs."),
            Part(HOOKS, "hooks", '{"hooks": {}}'),
            Part(EXECUTABLE, "validate-tests.sh", "#!/bin/sh\npytest\n", executable=True),
            Part(MCP, "servers", '{"mcpServers": {}}'),
        ],
    )


def test_copilot_is_a_distinct_identity_from_vscode_copilot():
    assert "copilot" in PACKAGING
    assert PACKAGING["copilot"]["unit"] == "plugin"
    assert PACKAGING["vscode_copilot"]["unit"] is None


def test_plan_renders_the_real_bundle_layout(bundle):
    """The exact directory shape from the vendor's own example, component-for-component."""
    result = packaging.plan("copilot", bundle)
    assert result.root == "my-testing-plugin"
    assert "skills/test-runner/SKILL.md" in result.files
    assert "com.github.copilot/agents/test-reviewer.agent.md" in result.files
    assert "com.github.copilot/hooks/hooks.json" in result.files
    assert "scripts/validate-tests.sh" in result.files
    assert "mcp.json" in result.files
    assert result.executables == {"scripts/validate-tests.sh"}


def test_the_manifest_declares_the_agent_plugins_schema(bundle):
    """Load-bearing, not decorative: no $schema falls back to the unrelated Legacy format."""
    result = packaging.plan("copilot", bundle)
    manifest = json.loads(result.files["plugin.json"])
    assert manifest["$schema"] == "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
    assert manifest["name"] == "my-testing-plugin"
    assert manifest["version"] == "1.2.0"


def test_the_executable_is_reachable_via_the_agent_plugins_1_0_token(bundle):
    """${PLUGIN_ROOT}, not ${CLAUDE_PLUGIN_ROOT} -- the Legacy Copilot format's spelling."""
    result = packaging.plan("copilot", bundle)
    ref = packaging.executable_ref("copilot", "scripts/validate-tests.sh")
    assert ref == "${PLUGIN_ROOT}/scripts/validate-tests.sh"
    assert result.complete


def test_a_skill_here_is_the_same_path_every_other_plugin_format_uses():
    """The module's central claim, extended: Copilot's skill path is not a fifth spelling."""
    shared = packaging.same_path_for(SKILL)["skills/{name}/SKILL.md"]
    assert "copilot" in shared
    assert PACKAGING["copilot"]["parts"][SKILL] == "skills/{name}/SKILL.md"


def test_slash_commands_have_no_established_file_format():
    """com.github.copilot/commands/ is documented; the file extension inside it is not."""
    result = packaging.plan("copilot", Bundle("b", parts=[Part(COMMAND, "run", "some prompt")]))
    assert not result.complete
    assert result.unrepresentable[0].reason == PART_LIMITS[("copilot", COMMAND)]


def test_copilot_is_unadapted_but_not_unverified():
    """No adapter is registered (it would collide with vscode_copilot's), but it is not a
    stale inherited guess either -- the matrix row documents real, cited vendor evidence."""
    from agentseam import adapters
    from agentseam.matrix import basis
    from agentseam.matrix_terms import BASIS_DOCS, BASIS_INHERITED

    assert "copilot" not in adapters.ADAPTERS
    assert "copilot" in GAPS
    assert basis("copilot") == BASIS_DOCS
    assert basis("copilot") != BASIS_INHERITED
