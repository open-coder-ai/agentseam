"""How each matrix row's claims were established, kept apart from the claims themselves.

Row-level `EVIDENCE` and per-claim cell records used to live in two files
(`matrix-evidence.json` duplicated `matrix.json`'s own `verified` byte-for-byte). This module
is now the one place that reads `matrix.json` for provenance; `EVIDENCE` is derived from it
rather than loaded from a second copy.
"""

from __future__ import annotations

from ._data import load
from .matrix_terms import (
    BASES,
    BASIS_DOCS,
    BASIS_LIVE_PARTIAL,
    CLAIM_FIELDS,
    OPTIONAL_CLAIM_FIELDS,
    REQUIRED_CLAIM_FIELDS,
)

_RAW = load("matrix.json")

#: agent -> that row's verification record. Derived from matrix.json's own `verified`
#: rather than a second file, so there is exactly one place this can go stale.
EVIDENCE = {agent: row["verified"] for agent, row in _RAW.items()}


def claim_record(row, event, field):
    """The evidence record backing one (event, field) claim on `row`.

    An explicit override under `cell["evidence"][field]` wins; otherwise the row's own
    `verified` record applies -- a claim with no per-claim evidence still rests on
    whatever the row as a whole does, never on nothing.
    """
    cell = row.get("events", {}).get(event, {})
    override = (cell.get("evidence") or {}).get(field)
    if override:
        return override
    verified = row.get("verified") or {}
    return {
        "basis": verified.get("basis"),
        "date": verified.get("date"),
        "version": verified.get("version"),
        "method": verified.get("method"),
    }


def claim_basis(row, event, field):
    """The basis backing one (event, field) claim -- what `enforcement_level` caps a grade by.

    A row basis of `live-run-partial` only backs the events its own `verified.observed`
    actually names -- that is the whole point of the "partial" word. An event the row
    claims but never watched falls back to `verified.fallback_basis` (what the rest of the
    row rests on: source, documentation, ...), defaulting to `vendor-docs` when the row
    does not say. Without this, a claim seeded mechanically from the row (or one that
    simply inherits the row for lack of its own record) would let an unobserved event grade
    as high as `enforced`, which is exactly the class of bug `cap_grade` exists to close.
    """
    basis = claim_record(row, event, field).get("basis")
    verified = row.get("verified") or {}
    if basis == BASIS_LIVE_PARTIAL and event not in verified.get("observed", ()):
        return verified.get("fallback_basis", BASIS_DOCS)
    return basis


def validate_claim(record):
    """Error strings for one evidence record; empty means it is well-formed. Never raises."""
    if not isinstance(record, dict):
        return ["not an object: %r" % (record,)]
    errors = []
    if record.get("basis") not in BASES:
        errors.append("basis %r is not one of %s" % (record.get("basis"), BASES))
    date = record.get("date")
    if not (isinstance(date, str) and len(date) == len("YYYY-MM-DD") and date.count("-") == 2):  # noqa: PLR2004
        errors.append("date %r is not YYYY-MM-DD" % (date,))
    has_test, has_method = bool(record.get("test")), bool(record.get("method"))
    if has_test == has_method:
        errors.append(
            "must carry exactly one of `test` or `method`, got test=%r method=%r"
            % (record.get("test"), record.get("method"))
        )
    return errors


def validate_cell(cell):
    """Error strings for one matrix cell's evidence coverage; empty means it is complete.

    Every required field (`block`, `rewrite`, `fail_mode`) must carry a record. An optional
    field (`silence_means`, `timeout_fail_mode`, `unknown_verb_means`) needs one only when
    the cell actually asserts it -- absence of the key is not a claim, and carries none.
    """
    evidence = cell.get("evidence") or {}
    errors = []
    for field in REQUIRED_CLAIM_FIELDS:
        errors.extend(_field_errors(field, evidence.get(field)))
    for field in OPTIONAL_CLAIM_FIELDS:
        if field in cell:
            errors.extend(_field_errors(field, evidence.get(field)))
    return errors


def _field_errors(field, record):
    if record is None:
        return ["%s: no evidence record" % field]
    return ["%s: %s" % (field, e) for e in validate_claim(record)]


__all__ = [
    "CLAIM_FIELDS",
    "EVIDENCE",
    "claim_basis",
    "claim_record",
    "validate_cell",
    "validate_claim",
]
