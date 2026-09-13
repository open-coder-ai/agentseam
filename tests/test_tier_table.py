"""The derived enforcement table: every column comes from the matrix, none from a consumer."""

from __future__ import annotations

import pytest

from agentseam import tier_table
from agentseam.contract import PRE_TOOL
from agentseam.matrix import MATRIX, enforcement_level


def test_every_matrix_row_appears_exactly_once():
    agents = [r["agent"] for r in tier_table.rows()]
    assert agents == sorted(MATRIX)


def test_the_grade_column_is_the_capped_grade_not_the_raw_cell():
    """The point of deriving: a row cannot print a grade its basis will not support."""
    for row in tier_table.rows():
        assert row["grade"] == enforcement_level(row["agent"], PRE_TOOL)


def test_no_row_claims_enforced_on_a_documentation_basis():
    """Grading never exceeds basis, asserted on the rendered output rather than the helper."""
    for row in tier_table.rows():
        if row["basis"] in ("vendor-docs", "third-party-install", "inherited"):
            assert row["grade"] != "enforced", row


def test_an_agent_with_no_hook_surface_prints_not_applicable_not_a_weak_fail_mode():
    """There is nothing to fail; saying so keeps the absence visible."""
    for name in tier_table.unadapted():
        row = next(r for r in tier_table.rows() if r["agent"] == name)
        assert row["fail_mode"] == tier_table.NOT_APPLICABLE


def test_markdown_has_a_header_a_rule_and_one_line_per_agent():
    lines = tier_table.markdown().splitlines()
    assert lines[1].strip("|").split("|") == ["---"] * len(tier_table.COLUMNS)
    assert len(lines) == len(MATRIX) + 2


def test_markdown_renders_every_column_it_was_asked_for():
    out = tier_table.markdown(columns=("agent", "grade"))
    assert out.splitlines()[0] == "| Agent | Grade |"
    assert len(out.splitlines()[2].strip("|").split("|")) == 2


def test_a_column_this_table_does_not_own_is_refused():
    """`Enforced` is the consumer's wiring column: agentseam has no way to know it."""
    with pytest.raises(ValueError) as exc:
        tier_table.markdown(columns=("agent", "enforced"))
    assert "enforced" in str(exc.value)


def test_no_consumer_vocabulary_leaks_into_this_module():
    """chock's tier names and wiring words may never be rendered by the engine."""
    import pathlib

    rendered = tier_table.markdown()
    for word in ("T1", "T2", "T3", "hook + CI", "CI only", "chock"):
        assert word not in rendered
    source = pathlib.Path(tier_table.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]
    assert "chock" not in body


def test_the_table_is_per_event():
    """An agent that can block at one gate and not another must not read the same at both."""
    events = {e for row in MATRIX.values() for e in row["events"]}
    grades = {ev: {r["agent"]: r["grade"] for r in tier_table.rows(ev)} for ev in events}
    assert len({tuple(sorted(g.items())) for g in grades.values()}) > 1


def test_an_event_no_agent_supports_yields_a_table_of_absences():
    rows = tier_table.rows("no_such_event")
    assert rows
    assert {r["fail_mode"] for r in rows} == {tier_table.NOT_APPLICABLE}
    assert {r["grade"] for r in rows} == {"none"}
