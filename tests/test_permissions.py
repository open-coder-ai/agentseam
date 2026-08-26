"""Primitive 4 tests.

Most of these guard one property: that a rendered policy never claims more than the agent
can enforce. The renderers are easy to make "helpful" in exactly the wrong way -- emitting a
nearby key that looks like a deny -- so the tests assert on what comes back in the
`unrepresentable` list as carefully as on what comes back in the fragment.
"""

from __future__ import annotations

import pytest

from agentseam import permissions
from agentseam.permissions import Rule
from agentseam.permissions_data import (
    ACTIONS,
    ALLOW,
    ASK,
    CAPABILITIES,
    CAPABILITY,
    CONFIG_FILES,
    DENY,
    FILE_WRITE,
    SHELL,
    UNRECORDED,
)


def test_rule_rejects_vocabulary_it_does_not_know():
    with pytest.raises(ValueError):
        Rule("forbid", SHELL)
    with pytest.raises(ValueError):
        Rule(DENY, "telepathy")


@pytest.mark.parametrize("agent", sorted(CAPABILITY))
def test_every_agent_declares_all_three_actions_even_when_the_answer_is_no(agent):
    """A missing key would read as an oversight; an explicit None is a claim we stand behind."""
    actions = CAPABILITY[agent]["actions"]
    assert set(actions) == set(ACTIONS)


@pytest.mark.parametrize("agent", sorted(CAPABILITY))
def test_every_agent_records_how_it_was_verified(agent):
    verified = CAPABILITY[agent]["verified"]
    assert verified["method"] and verified["date"]


@pytest.mark.parametrize("agent", sorted(CAPABILITY))
def test_every_agent_maps_every_capability(agent):
    """Empty tuple means "this agent has no tool for that"; an absent key means we forgot."""
    assert set(CAPABILITY[agent]["tools"]) == set(CAPABILITIES)


@pytest.mark.parametrize("agent", sorted(CAPABILITY))
def test_every_agent_has_somewhere_to_write(agent):
    assert CONFIG_FILES[agent]


def test_unrecorded_agents_are_not_silently_rendered_as_empty_config():
    """The dangerous failure is a valid-looking empty policy for an agent we know nothing about."""
    for agent in UNRECORDED:
        assert agent not in CAPABILITY
        with pytest.raises(KeyError):
            permissions.plan(agent, [Rule(DENY, SHELL, "curl")])


def test_vscode_deny_is_reported_rather_than_written_as_a_false_entry():
    """`{"pattern": false}` withholds auto-approval; it does not block. It must never render a deny."""
    result = permissions.plan("vscode_copilot", [Rule(DENY, SHELL, "curl *")])
    assert result.fragment == {}
    assert not result.complete
    assert "would not block" in result.unrepresentable[0].reason
    assert permissions.expresses("vscode_copilot", DENY) is None
    assert permissions.deny_is_authoritative("vscode_copilot") is False


def test_vscode_ask_and_allow_share_one_key_with_opposite_values():
    result = permissions.plan("vscode_copilot", [Rule(ALLOW, SHELL, "npm test"), Rule(ASK, SHELL, "git push")])
    assert result.fragment["chat.tools.terminal.autoApprove"] == {"npm test": True, "git push": False}
    assert result.complete


def test_gemini_cannot_deny_a_subset_of_a_tools_invocations():
    """tools.exclude drops a tool by name, so a specifier-scoped deny has no expression."""
    narrow = permissions.plan("gemini_cli", [Rule(DENY, SHELL, "curl *")])
    assert not narrow.complete
    assert "whole tool" in narrow.unrepresentable[0].reason

    whole = permissions.plan("gemini_cli", [Rule(DENY, SHELL)])
    assert whole.complete
    assert whole.fragment == {"tools": {"exclude": ["run_shell_command"]}}


def test_claude_code_renders_one_rule_onto_every_tool_that_carries_the_capability():
    result = permissions.plan("claude_code", [Rule(DENY, FILE_WRITE, ".env")])
    assert result.complete
    assert result.fragment["permissions"]["deny"] == ["Edit(.env)", "Write(.env)"]


def test_codex_renders_shell_rules_as_prefix_rules_and_drops_the_rest():
    result = permissions.plan("codex_cli", [Rule(DENY, SHELL, "curl example.com"), Rule(DENY, FILE_WRITE, ".env")])
    assert 'pattern = ["curl", "example.com"]' in result.fragment
    assert 'decision = "forbidden"' in result.fragment
    assert len(result.unrepresentable) == 1
    assert result.unrepresentable[0].rule.capability == FILE_WRITE


def test_a_bare_rule_needing_a_specifier_is_dropped_rather_than_matching_everything():
    """A prefix rule with no prefix, or an auto-approve entry with no pattern, is a footgun."""
    for agent in ("codex_cli", "vscode_copilot"):
        result = permissions.plan(agent, [Rule(ALLOW, SHELL)])
        assert not result.complete, agent


def test_plan_targets_the_project_file_not_the_administrator_one():
    """managed-settings.json outranks the rest; pointing a project policy there would be wrong."""
    assert permissions.config_files("claude_code")[0]["scope"] == "managed"
    assert permissions.plan("claude_code", []).path == ".claude/settings.json"


def test_config_files_are_ordered_by_precedence_and_returned_as_copies():
    rows = permissions.config_files("claude_code")
    assert [r["scope"] for r in rows] == ["managed", "local", "project", "user"]
    rows[0]["path"] = "mutated"
    assert permissions.config_files("claude_code")[0]["path"] == "managed-settings.json"


def test_discover_probes_project_files_only(tmp_path):
    """A user-scoped miss would report on this process's HOME, not on the machine."""
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").write_text("{}")
    found = permissions.discover(str(tmp_path))
    assert list(found) == ["claude_code"]
    assert [row["scope"] for row in found["claude_code"]] == ["project"]


def test_every_agent_with_a_permission_model_is_an_agent_the_matrix_knows():
    from agentseam.matrix import MATRIX

    assert set(CAPABILITY) <= set(MATRIX)
    assert set(UNRECORDED) <= set(MATRIX)


def test_every_matrix_agent_is_accounted_for():
    """Recorded plus unrecorded must equal the matrix, exactly.

    This is the invariant the module is for. An agent missing from both tables reads as
    "nothing to say here" when the truth is "nobody looked" -- and four agents sat in that
    state after their adapters landed, because nothing forced the tables to keep up. Adding
    an agent to the matrix now fails here until somebody records what its config can say,
    or states plainly that it is unknown.
    """
    from agentseam.matrix_data import MATRIX

    assert set(CAPABILITY) | set(UNRECORDED) == set(MATRIX)


def test_an_agent_is_never_both_recorded_and_unrecorded():
    assert not set(CAPABILITY) & set(UNRECORDED)


def test_no_unrecorded_reason_is_empty():
    """A blank reason is worse than no row: it looks answered."""
    assert all(reason.strip() for reason in UNRECORDED.values())


def test_a_missing_hook_surface_is_not_recorded_as_a_missing_permission_model():
    """Two unrelated facts. Aider and Zed expose no hooks; that says nothing about what
    their config files can restrict, and the reasons say so rather than conflating them.
    """
    for agent in ("aider", "zed"):
        assert "independent of its lack of a hook surface" in UNRECORDED[agent]
