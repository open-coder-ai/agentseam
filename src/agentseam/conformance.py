"""Whether a policy's verdict differing between vendors is the vendor's fault or ours.

Owner decision, 2026-09-13: a policy is tested against the seam; the seam is tested
against the vendors, once. Running a new policy per vendor is not extra rigour -- it is a
seam gap paid for twice. That rule needs one thing before it can be enforced rather than
quoted: a definition of the difference that condemns this layer, as opposed to the
differences that are simply true about the world.

The line drawn here:

    A policy's verdict must be identical across every vendor that CAN reach it.
    Where a vendor cannot, the shortfall is reported, never papered over.

So `copilot` failing open where others fail closed is not a gap -- it is a true property of
that vendor, and the matrix says so out loud. A verdict that differs between two vendors
the matrix says are equally capable is the other thing entirely: nothing about the world
explains it, so it is this layer leaking a dialect into a policy's result. That is the
"half cooked" signal, and SEAM_GAP is its name.

Naming, deliberately not `drift`: `staleness.DRIFTED` already means a vendor shipped a new
version since a row was recorded. Same English word, unrelated question, and this track has
lost time to exactly that kind of collision before.

One refusal carries the honesty: a vendor with no matrix row is never excused. Treating an
unrecorded vendor as "cannot enforce" would let any divergence be waved through by the mere
absence of evidence, which is the papering-over the rule exists to forbid.
"""

from __future__ import annotations

from .matrix import MATRIX, can_block, can_rewrite, enforcement_level

#: Every vendor asked returned the same verdict. The policy is answerable for it.
AGREED = "agreed"
#: Verdicts differ, and every divergence is a shortfall the matrix already records.
VENDOR_LIMIT = "vendor-limit"
#: Verdicts differ between vendors the matrix says are equally able. A seam defect.
SEAM_GAP = "seam-gap"
#: A vendor in the comparison has no recorded capability, so nothing can be concluded.
UNDECIDABLE = "undecidable"

VERDICTS = (AGREED, VENDOR_LIMIT, SEAM_GAP, UNDECIDABLE)

#: What a policy needs of a vendor to reach a given verdict. A policy that must stop an
#: action needs `block`; one that must repair it needs `rewrite`. Anything else asks only
#: that the vendor let the hook run at all.
NEEDS_BLOCK = "block"
NEEDS_REWRITE = "rewrite"
NEEDS_NOTHING = None


#: Raised as a message constant so the text is not a literal inside the raise (TRY003).
_NOTHING_TO_COMPARE = "no verdicts to compare: a policy that ran nowhere has no conformance"

#: Below this, there is no cross-vendor question to answer.
_MIN_VENDORS = 2


class UnrecordedVendorError(LookupError):
    """A vendor in the comparison has no matrix row, so its divergence cannot be judged."""


def capable(agent, event, *, needs=NEEDS_BLOCK):
    """Whether `agent` can reach a verdict requiring `needs` at `event`.

    Raises UnrecordedVendorError rather than answering False for an agent with no row: "we never
    looked" and "the vendor cannot" are different answers and must not share one.
    """
    if agent not in MATRIX:
        raise UnrecordedVendorError(
            "%r has no matrix row, so a verdict difference involving it cannot be called a "
            "vendor limit. Record the row, or leave it out of the comparison." % agent
        )
    if needs == NEEDS_BLOCK:
        return can_block(agent, event)
    if needs == NEEDS_REWRITE:
        return can_rewrite(agent, event)
    return bool(MATRIX[agent]["events"].get(event))


def classify(verdicts, event, *, needs=NEEDS_BLOCK):
    """Why `verdicts` (agent -> policy verdict) differ, from the VERDICTS vocabulary.

    Returns a dict carrying the call, the verdict groups, and which agents are excused --
    enough for a caller to print a finding without re-deriving any of it.
    """
    if not verdicts:
        raise ValueError(_NOTHING_TO_COMPARE)
    groups = _groups(verdicts)

    # One vendor is not a comparison. It will always "agree", and reporting that as AGREED
    # claims a cross-vendor check that never happened -- the same mistake as reading unanimity
    # among incapable vendors as agreement, one row further out. Note this is about the number
    # of vendors ASKED, not how many can enforce: one capable vendor beside one excused one is
    # a real vendor-limit finding and still classifies as one.
    if len(verdicts) < _MIN_VENDORS:
        return _result(
            UNDECIDABLE,
            groups,
            event,
            (),
            reason="only %s was asked: conformance is a comparison, and one vendor cannot differ "
            "from anything" % next(iter(verdicts)),
        )

    try:
        excused = tuple(sorted(a for a in verdicts if not capable(a, event, needs=needs)))
    except UnrecordedVendorError as exc:
        return _result(UNDECIDABLE, groups, event, (), reason=str(exc))

    # Capability is settled BEFORE agreement, because unanimity among vendors that cannot
    # enforce is not agreement about the policy -- it is the absence of a test, and the two
    # must never return the same call. An earlier revision short-circuited on agreement
    # first and reported two incapable vendors as AGREED.
    capable_verdicts = _groups({a: v for a, v in verdicts.items() if a not in excused})
    if not capable_verdicts:
        return _result(
            UNDECIDABLE,
            groups,
            event,
            excused,
            reason="no vendor in the comparison can enforce at %r, so the policy was never tested" % event,
        )

    if len(groups) == 1:
        return _result(AGREED, groups, event, excused)
    if len(capable_verdicts) == 1:
        return _result(VENDOR_LIMIT, groups, event, excused)
    return _result(SEAM_GAP, groups, event, excused)


def _groups(verdicts):
    """Verdict -> the agents that returned it, as sorted tuples."""
    out = {}
    for agent, verdict in verdicts.items():
        out.setdefault(_key(verdict), []).append(agent)
    return {v: tuple(sorted(a)) for v, a in out.items()}


def _key(verdict):
    """A verdict's comparable form. Dicts and lists arrive from JSON and are unhashable."""
    if isinstance(verdict, dict):
        return tuple(sorted((k, _key(v)) for k, v in verdict.items()))
    if isinstance(verdict, (list, tuple)):
        return tuple(_key(v) for v in verdict)
    return verdict


def _result(call, groups, event, excused, reason=None):
    """The classification, with `offenders` derived rather than passed.

    Only a SEAM_GAP has offenders, and they are exactly the vendors that were not excused --
    deriving it here means a caller cannot name offenders on a call that has none.
    """
    agents_seen = {a for names in groups.values() for a in names}
    offenders = tuple(sorted(agents_seen - set(excused))) if call == SEAM_GAP else ()
    return {
        "call": call,
        "event": event,
        "groups": groups,
        "excused": tuple(excused),
        "offenders": offenders,
        "reason": reason or _REASONS[call],
    }


_REASONS = {
    AGREED: "every vendor asked returned the same verdict",
    VENDOR_LIMIT: "the vendors that differ are ones the matrix already records as unable to enforce here",
    SEAM_GAP: "vendors the matrix says are equally able returned different verdicts -- the seam is leaking a dialect",
    UNDECIDABLE: "the comparison cannot be judged",
}


def is_seam_gap(verdicts, event, *, needs=NEEDS_BLOCK):
    """Whether this comparison condemns agentseam. The one-line form for a CI gate."""
    return classify(verdicts, event, needs=needs)["call"] == SEAM_GAP


def shortfalls(agents, event, *, needs=NEEDS_BLOCK):
    """Agent -> the honest grade, for every agent that cannot enforce at `event`.

    The reporting half of the rule: a vendor that cannot enforce is named with what it can
    actually claim, so the shortfall appears in the output instead of being smoothed away.
    """
    out = {}
    for agent in agents:
        if not capable(agent, event, needs=needs):
            out[agent] = enforcement_level(agent, event)
    return out
