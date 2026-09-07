"""How old a row's evidence is, and whether the agent has moved since it was taken.

Evidence does not decay gracefully: a `live-run` against Claude Code 2.1.247 says nothing
about 2.1.263 if the hook contract changed in between, and nothing in a data file notices.
This module is the arithmetic behind noticing -- kept here, in the runtime, rather than in
the tool that fetches versions, so `doctor`, `matrix` and CI all read staleness the same
way instead of each rolling its own threshold.

It deliberately does no I/O. Comparing a recorded version against the current one requires
knowing the current one, and finding that out is a network act that belongs in
tools/watch_versions.py. Everything here is a pure function of data already on disk.

The design bet, stated in full: **displaying staleness is better than hiding it.** A row
that says "verified against 3.17.8, 87 days ago" is more useful than one that silently
implies it is current, and it removes the pressure to re-run sixteen agents on a schedule
nobody can afford. Age is not a failure. Unreported age is.
"""

from __future__ import annotations

from datetime import date

#: Past this, a row is old enough that nobody should rely on it without re-checking.
#: Not a hard error: plenty of agents go a quarter without touching their hook contract.
STALE_AFTER_DAYS = 90

#: Bases that make an age meaningful. A `vendor-docs` row was never a measurement, so its
#: age measures how long ago someone read a web page -- worth showing, not worth alarming
#: about. Only rows that once touched a running agent can go stale in the sense that
#: matters.
MEASURED_BASES = ("live-run", "live-run-partial")

FRESH = "fresh"
STALE = "stale"
DRIFTED = "drifted"
UNDATED = "undated"
UNMEASURED = "unmeasured"
#: Measured, dated, recent -- but the current version could not be established, so no
#: comparison happened. Distinct from FRESH on purpose: an unreachable release feed must
#: never read as "still current", or a broken watcher becomes an assurance.
UNCHECKED = "unchecked"


def age_days(evidence, today=None):
    """Days since this evidence was taken, or None if it carries no usable date."""
    raw = (evidence or {}).get("date")
    if not raw:
        return None
    try:
        parts = [int(x) for x in str(raw).split("-")]
        taken = date(*parts)
    except (TypeError, ValueError):
        return None
    return ((today or date.today()) - taken).days


def parse_version(text):
    """A comparable tuple from a version string, or () when it is not one.

    Leading numeric components only: `2.1.263` -> (2, 1, 263), `1.0.0-beta.2` -> (1, 0, 0).
    Pre-release ordering is deliberately not modelled. Knowing that a recorded version is
    *behind* is the whole requirement, and inventing a total order over every vendor's
    tagging habits would be a large amount of code standing between a fact and its reader.
    """
    out = []
    for chunk in str(text or "").replace("-", ".").replace("+", ".").split("."):
        digits = ""
        for ch in chunk:
            if not ch.isdigit():
                break
            digits += ch
        if not digits:
            break
        out.append(int(digits))
    return tuple(out)


def is_behind(recorded, current):
    """True when `recorded` is an older version than `current`.

    None where either side is missing or unparseable -- an unknown is reported as unknown
    rather than defaulting to "fine", because a default of "fine" is how a stale row stays
    invisible.
    """
    a, b = parse_version(recorded), parse_version(current)
    if not a or not b:
        return None
    width = max(len(a), len(b))
    a = a + (0,) * (width - len(a))
    b = b + (0,) * (width - len(b))
    return a < b


def status(evidence, current_version=None, today=None, stale_after=STALE_AFTER_DAYS):
    """One row's freshness, as a dict the CLI and CI both render.

    `drifted` outranks `stale`: a row whose agent has shipped a new version is a sharper
    signal than one that is merely old, and it is the signal a watcher can produce without
    anyone running an agent.
    """
    evidence = evidence or {}
    days = age_days(evidence, today=today)
    behind = is_behind(evidence.get("version"), current_version)
    basis = evidence.get("basis")

    if basis not in MEASURED_BASES:
        verdict = UNMEASURED
    elif behind:
        verdict = DRIFTED
    elif days is None:
        verdict = UNDATED
    elif days > stale_after:
        verdict = STALE
    elif behind is None:
        # Recent and measured, but nothing compared it to a current version -- either the
        # release feed was unreachable, none is known, or the recorded "version" is prose
        # rather than a version. Reporting this as FRESH is how a stale row hides.
        verdict = UNCHECKED
    else:
        verdict = FRESH

    return {
        "verdict": verdict,
        "basis": basis,
        "age_days": days,
        "recorded_version": evidence.get("version"),
        "current_version": current_version,
        "behind": behind,
        # A recorded version that does not parse can never be compared, however good the
        # release feed is. Surfaced so the fix (record a version) is obvious.
        "version_comparable": bool(parse_version(evidence.get("version"))),
    }


def summarize(state):
    """One line a human can read, from a status() dict."""
    bits = [state["verdict"]]
    if state["recorded_version"]:
        bits.append(str(state["recorded_version"]))
    if state["behind"] and state["current_version"]:
        bits.append("-> %s available" % state["current_version"])
    if state["age_days"] is not None:
        bits.append("%d days old" % state["age_days"])
    return ", ".join(bits)
