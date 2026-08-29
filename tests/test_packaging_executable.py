"""Tests for the EXECUTABLE part (R1): the consumer-supplied script a HOOKS command runs.

Kept apart from test_packaging.py's general assertions -- this is one feature, exercised
per supporting format, and the pairing keeps each file under the 300-line budget.
"""

from __future__ import annotations

import pytest

from agentseam import packaging
from agentseam.packaging import Bundle, Part
from agentseam.packaging_data import EXECUTABLE, HOOKS, PACKAGING, PART_LIMITS, PARTS


def test_part_carries_an_executable_flag_defaulting_false():
    assert Part(EXECUTABLE, "guard", "#!/bin/sh\necho hi").executable is False
    assert Part(EXECUTABLE, "guard", "#!/bin/sh\necho hi", executable=True).executable is True


@pytest.mark.parametrize("agent", sorted(PACKAGING))
def test_every_agent_answers_the_executable_question(agent):
    """EXECUTABLE is a PART like any other: None is a claim, not a gap."""
    assert EXECUTABLE in PACKAGING[agent]["parts"]


@pytest.mark.parametrize("agent", ["claude_code", "gemini_cli", "vscode_copilot"])
def test_a_bundle_with_an_executable_and_hooks_renders_both(agent):
    """The acceptance shape from the spec: the file lands at the row's path, marked
    executable, and a hook command can reach it through the correct plugin_root token."""
    bundle = Bundle(
        "guard-bundle",
        parts=[
            Part(EXECUTABLE, "guard", "#!/bin/sh\necho blocked\nexit 2\n", executable=True),
            Part(HOOKS, "hooks", '{"hooks": {}}'),
        ],
    )
    result = packaging.plan(agent, bundle)
    assert result.complete

    template = PACKAGING[agent]["parts"][EXECUTABLE]
    expected_path = template.format(name="guard")
    assert expected_path in result.files
    assert result.executables == {expected_path}

    ref = packaging.executable_ref(agent, expected_path)
    row = PACKAGING[agent]
    if row["unit"] is None:
        assert ref == expected_path  # repo-local: nothing relocates, the path is the reference
    else:
        assert ref == "%s/%s" % (packaging.plugin_root(agent), expected_path)


@pytest.mark.parametrize("agent", ["codex_cli", "cursor"])
def test_an_unsupported_executable_is_reported_with_the_agents_own_reason(agent):
    """Manifest-resolving formats with no established executable slot refuse honestly."""
    bundle = Bundle("guard-bundle", parts=[Part(EXECUTABLE, "guard", "#!/bin/sh\necho hi")])
    result = packaging.plan(agent, bundle)
    assert not result.complete
    assert not result.executables
    assert result.unrepresentable[0].reason == PART_LIMITS[(agent, EXECUTABLE)]


def test_an_executable_part_not_marked_executable_still_renders_but_is_not_flagged():
    """`executable=False` places the file -- it just does not ask the writer to chmod it."""
    bundle = Bundle("b", parts=[Part(EXECUTABLE, "guard", "print('hi')")])
    result = packaging.plan("claude_code", bundle)
    assert "scripts/guard" in result.files
    assert result.executables == frozenset()


def test_plan_without_any_executable_part_reports_an_empty_frozenset():
    """Every existing caller gets an empty frozenset -- nothing that predates this breaks."""
    bundle = Bundle("b", parts=[Part(HOOKS, "hooks", "{}")])
    result = packaging.plan("claude_code", bundle)
    assert result.executables == frozenset()
    assert isinstance(result.executables, frozenset)


def test_executable_ref_returns_none_for_an_unrecorded_agent():
    assert packaging.executable_ref("not-a-real-agent", "scripts/x") is None


def test_executable_is_a_part_like_any_other():
    assert EXECUTABLE in PARTS
