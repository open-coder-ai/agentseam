"""The read-only verbs: what each agent can enforce, and how well that is known.

Split from cli.py by activity. These three report on evidence; everything left there
writes to a machine. Keeping them apart matters more than the line count it saves: a verb
that only prints is safe to run anywhere, and mixing the two made that hard to see.
"""

from __future__ import annotations

import json
from datetime import date

from . import install as install_mod
from . import recordings
from . import staleness as staleness_mod
from . import tier_table as tier_table_mod
from .contract import EVENTS
from .matrix import MATRIX, enforcement_level


def _cmd_matrix(args):
    if args.json:
        print(json.dumps(MATRIX, indent=2, sort_keys=True))
        return 0
    if args.evidence:
        return _print_evidence()
    events = [e for e in EVENTS if any(e in r["events"] for r in MATRIX.values())]
    width = max(len(e) for e in events)
    header = " " * (width + 2) + "  ".join("%-14s" % a for a in sorted(MATRIX))
    print(header)
    for ev in events:
        cells = "  ".join("%-14s" % enforcement_level(a, ev) for a in sorted(MATRIX))
        print("%-*s  %s" % (width, ev, cells))
    return 0


def _print_evidence():
    """How each row is known, and how old that knowledge is.

    Deliberately part of `matrix` rather than hidden behind `doctor`: the capability table
    and the provenance of its cells are the same claim, and showing one without the other
    is what lets a documentation guess pass for a measurement.
    """
    print("%-16s %-20s %-12s %-11s %-12s %s" % ("agent", "basis", "version", "verdict", "recorded", "date"))
    for name in sorted(MATRIX):
        verified = MATRIX[name]["verified"]
        state = staleness_mod.status(verified)
        print(
            "%-16s %-20s %-12s %-11s %-12s %s"
            % (
                name,
                verified.get("basis", "-"),
                str(verified.get("version", "-"))[:12],
                state["verdict"],
                recordings.latest_version(name) or "-",
                verified.get("date", "-"),
            )
        )
    print("\nrecorded: the newest data/recordings/<agent>@<version>.json, or '-' if never witnessed")
    print("verdicts: fresh (compared, current) | unchecked (no comparison was made)")
    print(
        "          stale (older than %d days) | unmeasured (never touched a running agent)"
        % staleness_mod.STALE_AFTER_DAYS
    )
    print("run tools/watch_versions.py to compare each row against its vendor's current release")
    return 0


def _cmd_doctor(args):
    """Report what is actually wired here, and how stale each capability claim is."""
    today = date.today()
    rc = 0
    for name in sorted(MATRIX):
        row = MATRIX[name]
        if row["tier"] == "none":
            print("%-16s no hook surface — %s" % (name, row["notes"].split(".")[0]))
            continue
        if row["tier"] == "unadapted":
            print("%-16s no hook adapter — instruction files only" % name)
            continue
        wired = install_mod.installed(name, args.repo)
        # No release feed is consulted here: `doctor` audits a machine and must work
        # offline. tools/watch_versions.py is what supplies a current version, and the
        # verdict vocabulary is shared so both surfaces read the same.
        state = staleness_mod.status(row["verified"], today=today)
        if state["verdict"] == staleness_mod.STALE:
            rc = 1
        print(
            "%-16s wired=%-5s verified=%s (%s)"
            % (name, "yes" if wired else "no", row["verified"].get("date", "?"), staleness_mod.summarize(state))
        )
    return rc


def cmd_tier_table(args):
    """Render the enforcement table a consumer would otherwise maintain by hand.

    Printed rather than written: which file it belongs in, and what wiring column joins onto
    it, are the consumer's business. agentseam owns the rows.
    """
    print(tier_table_mod.markdown(args.event))
    return 0
