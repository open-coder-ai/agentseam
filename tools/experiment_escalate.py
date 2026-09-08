#!/usr/bin/env python3
"""Classifying the `escalate` trial: a third state neither `deny` nor `silence` can reach.

Every other trial's observable is binary -- blocked, or not, per experiment.py's own
`_blocked()` (which already knows the stop gate's asymmetry: the sentinel there fires once
on the unhooked first pass regardless of trial, so "blocked" means a *re-fire*, not "the
sentinel stayed at zero"). Escalate adds a state that binary alone cannot distinguish: a
headless driver stuck waiting on a prompt nobody is there to answer looks exactly as
"blocked" as one that was cleanly refused. Telling them apart needs the driver's own
outcome alongside that verdict.

The exact rule, given `blocked` (experiment.py's own `_blocked()` result) and `outcome`
(the driver's result):

* Not blocked -> ``allow``: the action happened despite being asked to defer.
* Blocked, and the driver exited non-zero or timed out -> ``prompted``: the run ended
  waiting on an answer nobody gave, which is a different shape from a definite refusal.
* Blocked, and the driver exited cleanly -> ``refusal-or-error``: a decision was reached (a
  block, a fail-open default, whatever the vendor does) without ever running the action --
  the same vocabulary `silence_means`/`unknown_verb_means` already read blocked as.

The reference driver never reaches this module for the one gate where the ambiguity is
real (`PreToolUse`'s `permissionDecision: "ask"`): tools/reference_agent.py raises
`Undocumented` there instead, because nothing in Claude Code's own docs says what a
headless run does with nobody there to answer. Where the reference driver's gate degrades
`escalate` into a real block (a gate that does not honour it), it never stalls -- its
outcome carries neither `timed_out` nor a non-zero `returncode` -- so it can only ever
read `allow` or `refusal-or-error` here, never `prompted`.
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from agentseam.matrix_terms import (  # noqa: E402
    CLAIM_ESCALATE_MEANS,
    MEANS_ALLOW,
    MEANS_PROMPTED,
    MEANS_REFUSAL_OR_ERROR,
)


def driver_stalled(outcome):
    """Whether `outcome` (a driver's own result, not the sentinel) looks like a stall.

    The reference driver's outcome (`reference_agent.run_turn`'s return value) carries
    neither key and so never stalls by this reading -- it is fully scripted and always
    finishes. A real headless driver's outcome (tools/experiment_driver.drive_real) carries
    both.
    """
    if not outcome:
        return False
    if outcome.get("timed_out"):
        return True
    returncode = outcome.get("returncode")
    return returncode not in (0, None)


def classify_escalate(blocked, outcome):
    """(field, value, reading) for the escalate trial. See the module docstring for the rule."""
    if not blocked:
        return CLAIM_ESCALATE_MEANS, MEANS_ALLOW, "action ran despite being asked to defer"
    if driver_stalled(outcome):
        return CLAIM_ESCALATE_MEANS, MEANS_PROMPTED, "the run ended waiting on an answer nobody gave"
    return CLAIM_ESCALATE_MEANS, MEANS_REFUSAL_OR_ERROR, "a decision was reached without ever running the action"
