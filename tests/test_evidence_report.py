"""The submission trust boundary.

Reports arrive from strangers, so these tests are about provenance rather than plausibility.
A surprising measurement must pass -- that is the whole reason for accepting submissions --
while a report that overstates how it was obtained must not.
"""

from __future__ import annotations

import pytest

from agentseam import evidence_report as er
from agentseam.matrix_evidence import EVIDENCE


def _report(**kw):
    base = {
        "report_version": er.REPORT_VERSION,
        "agent": "cursor",
        "basis": "live-run-partial",
        "date": "2026-09-07",
        "driver": "real-agent",
        "version": "3.17.8",
    }
    base.update(kw)
    return base


def test_a_well_formed_report_validates():
    assert er.validate(_report())


@pytest.mark.parametrize("field", er.REQUIRED)
def test_every_required_field_is_required(field):
    bad = _report()
    del bad[field]
    with pytest.raises(er.InvalidReportError, match=field):
        er.validate(bad)


def test_unknown_fields_are_rejected_as_probable_typos():
    with pytest.raises(er.InvalidReportError, match="reporterr"):
        er.validate(_report(reporterr="@someone"))


def test_an_old_report_version_is_rejected_rather_than_half_read():
    with pytest.raises(er.InvalidReportError, match="Regenerate"):
        er.validate(_report(report_version=0))


def test_basis_must_come_from_the_closed_vocabulary():
    with pytest.raises(er.InvalidReportError, match="basis"):
        er.validate(_report(basis="looked-convincing"))


def test_the_reference_driver_cannot_claim_a_live_run():
    """The invariant the module exists for: documentation must not launder into measurement."""
    for basis in er.LIVE_BASES:
        with pytest.raises(er.InvalidReportError, match="documentation made executable"):
            er.validate(_report(driver=er.REFERENCE_DRIVER, basis=basis))


def test_the_reference_driver_may_still_report_documentation():
    assert er.validate(_report(driver=er.REFERENCE_DRIVER, basis="vendor-docs"))


def test_a_live_basis_requires_a_version():
    """Evidence that does not say which build it watched cannot be checked for drift."""
    bad = _report()
    del bad["version"]
    with pytest.raises(er.InvalidReportError, match="requires `version`"):
        er.validate(bad)


def test_a_surprising_measurement_is_accepted():
    """Rejecting results that contradict the matrix would make this confirm what we believe."""
    contradicts = _report(experiments={"block": False, "fail_mode": "closed"})
    assert er.validate(contradicts)


def test_dates_must_look_like_dates():
    with pytest.raises(er.InvalidReportError, match="YYYY-MM-DD"):
        er.validate(_report(date="last tuesday"))


def test_to_evidence_shapes_a_row():
    row = er.to_evidence(_report(reporter="@handle", notes="ran on Windows"))
    assert row["basis"] == "live-run-partial"
    assert row["version"] == "3.17.8"
    assert row["reporter"] == "@handle"
    assert row["method"] == "ran on Windows"


def test_diff_flags_a_basis_downgrade():
    """The change least likely to be intended and least likely to be spotted in review."""
    existing = EVIDENCE["claude_code"]
    assert existing["basis"] == "live-run"
    delta = er.diff_against(existing, _report(agent="claude_code", driver=er.REFERENCE_DRIVER, basis="vendor-docs"))
    assert delta["weakens_basis"] is True


def test_diff_does_not_flag_an_upgrade():
    existing = dict(EVIDENCE["cursor"], basis="vendor-docs")
    delta = er.diff_against(existing, _report(basis="live-run-partial"))
    assert delta["weakens_basis"] is False
    assert "basis" in delta["changes"]


def test_diff_writes_nothing():
    before = dict(EVIDENCE["cursor"])
    er.diff_against(EVIDENCE["cursor"], _report())
    assert EVIDENCE["cursor"] == before
