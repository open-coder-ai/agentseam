"""Per-claim evidence on matrix cells, and the grade cap that reads it (W53, 2026-09-07)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agentseam as A  # noqa: E402
from agentseam.matrix_evidence import validate_cell, validate_claim  # noqa: E402
from agentseam.matrix_terms import BASIS_DOCS, BASIS_LIVE, BASIS_LIVE_PARTIAL, FAIL_CLOSED  # noqa: E402


def test_every_asserted_cell_field_carries_evidence():
    """Task 1's shape rule: no claim on a live row is left without a record."""
    for agent, row in A.MATRIX.items():
        for event, cell in row["events"].items():
            errors = validate_cell(cell)
            assert not errors, "%s/%s: %s" % (agent, event, errors)


def test_a_cell_with_no_evidence_record_fails_the_shape_check():
    """The fixture the brief asks for: an asserted field with no record must fail."""
    errors = validate_cell({"block": True, "rewrite": False, "fail_mode": "open"})
    assert errors
    assert any("block" in e for e in errors)
    assert any("rewrite" in e for e in errors)
    assert any("fail_mode" in e for e in errors)


def test_an_evidence_record_needs_exactly_one_of_test_or_method():
    assert validate_claim({"basis": BASIS_DOCS, "date": "2026-09-01"})
    assert validate_claim({"basis": BASIS_DOCS, "date": "2026-09-01", "test": "t", "method": "both"})
    assert not validate_claim({"basis": BASIS_DOCS, "date": "2026-09-01", "method": "read the docs"})
    assert not validate_claim({"basis": BASIS_DOCS, "date": "2026-09-01", "test": "tests/test_matrix.py"})


def _row(basis, *, version=None, fail_mode=FAIL_CLOSED):
    record = {"basis": basis, "date": "2026-09-01", "method": "fixture"}
    if version:
        record["version"] = version
    return {
        "verified": dict(record),
        "events": {
            "pre_tool": {
                "block": True,
                "rewrite": False,
                "fail_mode": fail_mode,
                "evidence": {"block": record, "rewrite": record, "fail_mode": record},
            }
        },
    }


def test_grading_never_exceeds_basis():
    """Owner decision 2026-09-01, the failure that shipped as chock#89: a `vendor-docs`
    cell asserting fail-closed must not grade `enforced` -- only live evidence can back it."""
    A.MATRIX["_chock89_fixture"] = _row(BASIS_DOCS)
    try:
        assert A.enforcement_level("_chock89_fixture", A.PRE_TOOL) == "best-effort"
    finally:
        del A.MATRIX["_chock89_fixture"]


def test_a_live_run_backs_whatever_grade_the_cell_computes():
    A.MATRIX["_live_fixture"] = _row(BASIS_LIVE, version="1.0")
    try:
        assert A.enforcement_level("_live_fixture", A.PRE_TOOL) == "enforced"
    finally:
        del A.MATRIX["_live_fixture"]


def test_a_partial_live_run_only_backs_enforced_at_the_events_it_observed():
    """Task 3, W55: `live-run-partial` capped every unwatched event to `enforced` too, since
    a per-claim record seeded from the row (or one that simply falls back to it) carries the
    row's own basis regardless of `observed`. A fail-closed `stop` cell this row never
    watched must grade no higher than `best-effort` (the default fallback, `vendor-docs`,
    since this fixture sets no `fallback_basis` of its own)."""
    record = {"basis": BASIS_LIVE_PARTIAL, "date": "2026-09-01", "method": "fixture"}
    cell = {
        "block": True,
        "rewrite": False,
        "fail_mode": FAIL_CLOSED,
        "evidence": dict.fromkeys(("block", "rewrite", "fail_mode"), record),
    }
    A.MATRIX["_observed_fixture"] = {
        "verified": dict(record, observed=["pre_tool"]),
        "events": {"pre_tool": cell, "stop": cell},
    }
    try:
        assert A.enforcement_level("_observed_fixture", A.PRE_TOOL) == "enforced"
        assert A.enforcement_level("_observed_fixture", A.STOP) == "best-effort"
    finally:
        del A.MATRIX["_observed_fixture"]
