"""The vocabulary the matrix asserts in: fail modes, coverage tiers, and the cell shape."""

from __future__ import annotations

FAIL_CLOSED = "closed"
FAIL_OPEN = "open"
FAIL_CONFIGURABLE = "configurable"

TIER_FULL = "block+rewrite"
TIER_BLOCK = "block"
TIER_OBSERVE = "observe"
TIER_NONE = "none"
TIER_UNADAPTED = "unadapted"


def _cap(*, block=False, rewrite=False, fail=FAIL_OPEN):
    # "transform" is the ACS name for the same capability "rewrite" already recorded;
    # both keys carry the same value for one minor version (plan §1.6, item 4).
    return {"block": block, "rewrite": rewrite, "transform": rewrite, "fail_mode": fail}


BASIS_LIVE = "live-run"
BASIS_SOURCE = "vendor-source"
BASIS_DOCS = "vendor-docs"
BASIS_THIRD_PARTY = "third-party-install"
BASIS_LIVE_PARTIAL = "live-run-partial"
BASIS_INHERITED = "inherited"
#: Strongest first (org-plan plan/agentseam-project.md, 2026-09-01 decision). `diff_against`
#: and `cap_grade` both read strength as position in this tuple.
BASES = (BASIS_LIVE, BASIS_LIVE_PARTIAL, BASIS_SOURCE, BASIS_DOCS, BASIS_THIRD_PARTY, BASIS_INHERITED)

#: A per-claim record's two ways of saying how a claim was checked: `test` names an
#: automated check that exercises it against our runtime, `method` is prose for a claim
#: that rests on something a fixture cannot grant (a live run, a docs read). Exactly one
#: of the two is required, matching the vendor evidenceRecord's basis/date/test shape but
#: allowing prose where no automated check exists yet (matrix_evidence.validate_claim).
CLAIM_BLOCK = "block"
CLAIM_REWRITE = "rewrite"
CLAIM_FAIL_MODE = "fail_mode"
CLAIM_SILENCE_MEANS = "silence_means"
CLAIM_TIMEOUT_FAIL_MODE = "timeout_fail_mode"
CLAIM_UNKNOWN_VERB_MEANS = "unknown_verb_means"
CLAIM_ESCALATE_MEANS = "escalate_means"

#: Always present on every cell the row claims; each needs its own evidence record.
REQUIRED_CLAIM_FIELDS = (CLAIM_BLOCK, CLAIM_REWRITE, CLAIM_FAIL_MODE)
#: Present only where measured (task 3, 2026-09-07): absence is not a claim, so these need
#: evidence only on the cells that actually carry them.
OPTIONAL_CLAIM_FIELDS = (
    CLAIM_SILENCE_MEANS,
    CLAIM_TIMEOUT_FAIL_MODE,
    CLAIM_UNKNOWN_VERB_MEANS,
    CLAIM_ESCALATE_MEANS,
)
CLAIM_FIELDS = REQUIRED_CLAIM_FIELDS + OPTIONAL_CLAIM_FIELDS

#: The two-value vocabulary `silence_means` and `unknown_verb_means` answer in.
MEANS_ALLOW = "allow"
MEANS_REFUSAL_OR_ERROR = "refusal-or-error"
MEANS_VALUES = (MEANS_ALLOW, MEANS_REFUSAL_OR_ERROR)

#: `escalate_means` shares that vocabulary but adds a third state neither other field can
#: express: the run ended waiting on an answer nobody gave, rather than reaching either
#: `allow` or a definite refusal (tools/experiment_escalate.py classifies it).
MEANS_PROMPTED = "prompted"
ESCALATE_MEANS_VALUES = (MEANS_PROMPTED, MEANS_ALLOW, MEANS_REFUSAL_OR_ERROR)

GRADE_ENFORCED = "enforced"
GRADE_ENFORCEABLE = "enforceable"
GRADE_BEST_EFFORT = "best-effort"
GRADE_DETECT = "detect"
GRADE_NONE = "none"
#: Strongest first. A cap can only move a grade rightward (weaker), never left.
GRADE_ORDER = (GRADE_ENFORCED, GRADE_ENFORCEABLE, GRADE_BEST_EFFORT, GRADE_DETECT, GRADE_NONE)

#: Grading never exceeds basis (owner decision 2026-09-01): the strongest word a consumer
#: may say about a claim resting on `basis`, regardless of what the cell itself computes.
#: `live-run`/`live-run-partial` back any grade the cell computes; source, docs and a
#: third-party install top out at what watching from outside the vendor can honestly
#: support. `inherited` carries no first-hand look at all, so it is capped the same as docs.
GRADE_CEILING = {
    BASIS_LIVE: GRADE_ENFORCED,
    BASIS_LIVE_PARTIAL: GRADE_ENFORCED,
    BASIS_SOURCE: GRADE_ENFORCEABLE,
    BASIS_DOCS: GRADE_BEST_EFFORT,
    BASIS_THIRD_PARTY: GRADE_BEST_EFFORT,
    BASIS_INHERITED: GRADE_BEST_EFFORT,
}


def cap_grade(natural, basis):
    """The weaker of `natural` and the ceiling `basis` supports -- never the stronger."""
    ceiling = GRADE_CEILING.get(basis, GRADE_BEST_EFFORT)
    if GRADE_ORDER.index(natural) < GRADE_ORDER.index(ceiling):
        return ceiling
    return natural
