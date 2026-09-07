#!/usr/bin/env python3
"""Reading experiment results: against the matrix, and as a submittable report.

Split from experiment.py because producing a measurement and interpreting one are
different activities -- and because the interpretation is what a reviewer reads, so it
should be legible without wading through subprocess plumbing.
"""

from __future__ import annotations

import os
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from agentseam import contract, evidence_report, matrix_terms  # noqa: E402

#: Measured field -> the matrix cell key it corresponds to, derived from the cell's own
#: vocabulary (matrix_terms.CLAIM_FIELDS) rather than a hand-maintained partial table --
#: adding a claim field there is what makes it comparable here too, by construction. The
#: one rename: the "transform" trial measures the same claim the cell spells "rewrite".
_FIELD_ALIAS = {"transform": matrix_terms.CLAIM_REWRITE}


def _cell_key(field):
    field = _FIELD_ALIAS.get(field, field)
    return field if field in matrix_terms.CLAIM_FIELDS else None


def diff_against_matrix(results, event=contract.PRE_TOOL):
    """Measured vs asserted, per field. The point of the whole exercise.

    Agreement is not the interesting outcome -- it just means the row was right. A
    disagreement means either the matrix overclaims (a policy that silently fails) or
    underclaims (a capability being left on the table). A recognised field the cell simply
    does not carry (`silence_means` on a row that has never measured it) is `unasserted`,
    not a disagreement -- absence is not a claim (task 3, 2026-09-07). A field the matrix
    has no home for at all (`baseline_ok`, a run-health check, not a vendor claim) is
    `unrecorded`.
    """
    from agentseam import matrix

    cell = matrix.capability(results[0]["agent"], results[0].get("event", event))
    rows = []
    for r in results:
        ((field, measured),) = r["measured"].items()
        key = _cell_key(field)
        if key is None:
            status, claimed = "unrecorded", None
        elif key not in cell:
            status, claimed = "unasserted", None
        else:
            claimed = cell[key]
            status = "agrees" if claimed == measured else "DISAGREES"
        rows.append({"trial": r["trial"], "field": field, "measured": measured, "asserted": claimed, "status": status})
    return rows


def as_report(results, *, version=None, reporter=None, notes=None, today=None):
    """A submittable evidence report from a set of trial results.

    The basis is derived from the driver, never chosen by the caller: a run against the
    reference is documentation and says so. evidence_report.validate() enforces the same
    rule independently, so a hand-edited report cannot claim more than it earned.
    """
    driver = results[0]["driver"]
    measured = {}
    for r in results:
        measured.update(r["measured"])
    report = {
        "report_version": evidence_report.REPORT_VERSION,
        "agent": results[0]["agent"],
        "basis": "vendor-docs" if driver == evidence_report.REFERENCE_DRIVER else "live-run-partial",
        "date": (today or date.today()).isoformat(),
        "driver": "reference" if driver == evidence_report.REFERENCE_DRIVER else "real-agent",
        "experiments": measured,
        "platform": sys.platform,
    }
    for key, value in (("version", version), ("reporter", reporter), ("notes", notes)):
        if value:
            report[key] = value
    return evidence_report.validate(report)


def render(results, *, agent, event, driver):
    """The human table: measured beside asserted, disagreements named."""
    print("agent: %s   event: %s   driver: %s\n" % (agent, event, driver))
    print("%-10s %-20s %-14s %-14s %s" % ("trial", "field", "measured", "asserted", "status"))
    disagreements = 0
    for r, d in zip(results, diff_against_matrix(results)):
        disagreements += d["status"] == "DISAGREES"
        print(
            "%-10s %-20s %-14s %-14s %s" % (r["trial"], d["field"], str(d["measured"]), str(d["asserted"]), d["status"])
        )
    print()
    for r in results:
        print("  %-10s %s" % (r["trial"], r["reading"]))
    if disagreements:
        print("\n%d disagreement(s): the matrix and this agent do not match." % disagreements)
    return 0
