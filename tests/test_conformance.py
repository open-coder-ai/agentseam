"""Seam conformance: which verdict differences condemn this layer, and which do not."""

from __future__ import annotations

import pytest

from agentseam import conformance
from agentseam.contract import PRE_TOOL

# copilot is TIER_UNADAPTED and zed TIER_NONE, so neither can block at any event; both
# claude_code and cursor can. Asserted here so a matrix change breaks this file loudly
# rather than quietly turning these cases into different ones.
CAPABLE = ("claude_code", "cursor")
INCAPABLE = ("copilot", "zed")


def test_the_fixtures_this_file_rests_on_still_hold():
    for agent in CAPABLE:
        assert conformance.capable(agent, PRE_TOOL)
    for agent in INCAPABLE:
        assert not conformance.capable(agent, PRE_TOOL)


def test_unanimous_verdicts_are_agreement():
    result = conformance.classify({"claude_code": "blocked", "cursor": "blocked"}, PRE_TOOL)
    assert result["call"] == conformance.AGREED
    assert result["offenders"] == ()


def test_a_vendor_that_cannot_enforce_does_not_make_a_seam_gap():
    """copilot failing to block is a true property of copilot, recorded in the matrix."""
    result = conformance.classify({"claude_code": "blocked", "cursor": "blocked", "copilot": "allowed"}, PRE_TOOL)
    assert result["call"] == conformance.VENDOR_LIMIT
    assert result["excused"] == ("copilot",)


def test_two_equally_able_vendors_disagreeing_is_a_seam_gap():
    """Nothing about the world explains this, so it is this layer's defect."""
    verdicts = {"claude_code": "blocked", "cursor": "allowed"}
    result = conformance.classify(verdicts, PRE_TOOL)
    assert result["call"] == conformance.SEAM_GAP
    assert result["offenders"] == ("claude_code", "cursor")
    assert conformance.is_seam_gap(verdicts, PRE_TOOL)


def test_unanimity_among_vendors_that_cannot_enforce_is_not_agreement():
    """Regression: capability is settled before agreement.

    Two vendors that cannot enforce will always return the same thing. Reading that as
    AGREED reports an untested policy as a passing one -- the exact papering-over this
    module exists to forbid.
    """
    result = conformance.classify({"copilot": "allowed", "zed": "allowed"}, PRE_TOOL)
    assert result["call"] == conformance.UNDECIDABLE
    assert "never tested" in result["reason"]


def test_agreement_still_holds_when_an_excused_vendor_happens_to_agree():
    result = conformance.classify({"claude_code": "blocked", "cursor": "blocked", "copilot": "blocked"}, PRE_TOOL)
    assert result["call"] == conformance.AGREED
    assert result["excused"] == ("copilot",)


def test_an_unrecorded_vendor_is_never_excused():
    """Absence of evidence must not become a licence to wave a divergence through."""
    result = conformance.classify({"claude_code": "blocked", "notavendor": "allowed"}, PRE_TOOL)
    assert result["call"] == conformance.UNDECIDABLE
    assert "notavendor" in result["reason"]


def test_capable_raises_rather_than_answering_false_for_an_unknown_agent():
    with pytest.raises(conformance.UnrecordedVendorError):
        conformance.capable("notavendor", PRE_TOOL)


def test_rewrite_policies_are_judged_against_rewrite_capability():
    """A repair policy asks more of a vendor than a blocking one."""
    blockers = [a for a in conformance.MATRIX if conformance.can_block(a, PRE_TOOL)]
    assert blockers
    for agent in blockers:
        if not conformance.can_rewrite(agent, PRE_TOOL):
            assert conformance.capable(agent, PRE_TOOL, needs=conformance.NEEDS_BLOCK)
            assert not conformance.capable(agent, PRE_TOOL, needs=conformance.NEEDS_REWRITE)
            return


def test_verdicts_may_be_json_shaped_values():
    """Verdicts arrive from a harness's JSON: dicts and lists are unhashable as-is."""
    same = conformance.classify(
        {"claude_code": {"blocked": True, "at": ["pre_tool"]}, "cursor": {"blocked": True, "at": ["pre_tool"]}},
        PRE_TOOL,
    )
    assert same["call"] == conformance.AGREED
    differ = conformance.classify({"claude_code": {"blocked": True}, "cursor": {"blocked": False}}, PRE_TOOL)
    assert differ["call"] == conformance.SEAM_GAP


def test_shortfalls_names_every_vendor_that_cannot_enforce_with_its_honest_grade():
    out = conformance.shortfalls(list(CAPABLE) + list(INCAPABLE), PRE_TOOL)
    assert set(out) == set(INCAPABLE)
    assert all(grade for grade in out.values())


def test_an_empty_comparison_is_an_error_not_an_agreement():
    with pytest.raises(ValueError):
        conformance.classify({}, PRE_TOOL)


def test_every_call_carries_a_reason():
    for verdicts in (
        {"claude_code": "b", "cursor": "b"},
        {"claude_code": "b", "copilot": "a"},
        {"claude_code": "b", "cursor": "a"},
        {"copilot": "a", "zed": "a"},
    ):
        result = conformance.classify(verdicts, PRE_TOOL)
        assert result["call"] in conformance.VERDICTS
        assert result["reason"]


def test_the_word_drift_is_not_reused_for_this_concept():
    """staleness.DRIFTED already means a vendor shipped a new version. Same word, other question."""
    import pathlib

    for term in conformance.VERDICTS:
        assert "drift" not in term
    # Named once in the docstring so the collision is explicit; never in the code, where it
    # would be a second meaning for a word this package already spends.
    source = pathlib.Path(conformance.__file__).read_text(encoding="utf-8")
    body = source.split('"""', 2)[2]
    assert "drift" not in body


def test_one_vendor_alone_is_not_agreement():
    """Regression: a single vendor always "agrees" with itself.

    Found by wiring conformance over the recordings, where exactly one agent is witnessed --
    reporting AGREED there would have claimed a cross-vendor check that never ran. Same defect
    family as unanimity among incapable vendors, one row further out.
    """
    result = conformance.classify({"claude_code": "blocked"}, PRE_TOOL)
    assert result["call"] == conformance.UNDECIDABLE
    assert "cannot differ" in result["reason"]


def test_one_capable_vendor_beside_an_excused_one_is_still_a_real_finding():
    """The count that matters is vendors asked, not vendors capable."""
    result = conformance.classify({"claude_code": "blocked", "copilot": "allowed"}, PRE_TOOL)
    assert result["call"] == conformance.VENDOR_LIMIT
