"""The staleness watcher's per-agent drift issue: grouping, title, and self-sufficient body.

`check()`'s own network-touching path is exercised by test_staleness.py through the pure
`staleness` module; this file is about what happens once a row has already drifted --
grouping rows into one issue per agent, and the body a stranger with the agent installed
needs with nothing else.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

TOOLS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "tools")
sys.path.insert(0, TOOLS)

import watch_versions  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]

FIXTURE_ROWS = [
    {
        "agent": "claude_code",
        "event": "pre_tool",
        "verdict": "drifted",
        "recorded_version": "2.1.247",
        "current_version": "2.1.263",
        "age_days": 10,
    },
    {
        "agent": "claude_code",
        "event": "stop",
        "verdict": "drifted",
        "recorded_version": "2.1.247",
        "current_version": "2.1.263",
        "age_days": 10,
    },
    {
        "agent": "cursor",
        "event": None,
        "verdict": "unmeasured",
        "recorded_version": "3.17.0",
        "current_version": "3.18.0",
        "age_days": 5,
    },
]


def test_agents_needing_issues_groups_by_agent_and_skips_the_undrifted():
    grouped = watch_versions.agents_needing_issues(FIXTURE_ROWS)
    assert set(grouped) == {"claude_code"}
    assert len(grouped["claude_code"]) == 2


def test_issue_title_names_the_agent_and_the_new_version():
    title = watch_versions.issue_title("claude_code", "2.1.263")
    assert title == "evidence: claude_code 2.1.263 — re-witness wanted"


def test_issue_body_is_self_sufficient_for_a_stranger():
    """The verify command in the brief: agent, both versions, the --record command, both
    submission paths, and the honesty rule -- all present with nothing else to look up."""
    body = watch_versions.issue_body_for_agent(
        "claude_code", watch_versions.agents_needing_issues(FIXTURE_ROWS)["claude_code"]
    )
    assert "claude_code" in body
    assert "2.1.247" in body
    assert "2.1.263" in body
    assert "--record" in body
    assert "pip install agentseam" in body
    assert "open a PR" in body
    assert "Evidence report" in body
    assert "never counts as a re-witness" in body


def test_issue_body_only_suggests_gates_the_kit_can_gate_at():
    """claude_code's row claims post_tool, session_start, etc. -- experiment.py cannot wire
    a probe at any of those, so the suggested command must never name one."""
    body = watch_versions.issue_body_for_agent(
        "claude_code", watch_versions.agents_needing_issues(FIXTURE_ROWS)["claude_code"]
    )
    for event in ("pre_tool", "prompt_submit", "stop"):
        assert ("--event %s" % event) in body
    assert "--event post_tool" not in body


def test_issue_body_suggests_one_command_per_gate_not_a_repeated_flag():
    """tools/experiment.py's --event takes a single value; a comma- or repeat-flag command
    would silently only run the last gate."""
    body = watch_versions.issue_body_for_agent(
        "claude_code", watch_versions.agents_needing_issues(FIXTURE_ROWS)["claude_code"]
    )
    assert body.count("tools/experiment.py run") >= 2
    assert "--event pre_tool --event" not in body


def test_workflow_delegates_to_open_issues():
    """act-free assertion on the YAML: the report job is one call to --open-issues, which
    is unit-tested above for one-issue-per-agent and (via ISSUE_LABELS) both labels."""
    text = (ROOT / ".github" / "workflows" / "staleness.yml").read_text(encoding="utf-8")
    assert "--open-issues" in text
    assert "issues: write" in text


def test_open_issues_carries_both_labels():
    assert set(watch_versions.ISSUE_LABELS) == {"evidence", "help wanted"}
