#!/usr/bin/env python3
"""Check a submitted evidence report, and show what it would change.

Evidence arriving from people who own agents nobody here has a seat for is the only model
that keeps sixteen rows honest. That makes review the bottleneck, so this does the
mechanical half: is the report well-formed, does it claim more than its driver earned, and
which cells would move.

    python3 tools/verify_report.py report.json
    python3 tools/verify_report.py report.json --diff      # what the row would become
    cat report.json | python3 tools/verify_report.py -

It writes nothing. Merging a report into a row's evidence in matrix.json stays a human act with a
name on it -- the provenance of a row includes who decided to believe it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from agentseam import evidence_report  # noqa: E402
from agentseam.matrix_evidence import EVIDENCE  # noqa: E402


def _read(path):
    if path == "-":
        return json.load(sys.stdin)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _plain(value, keep="\n"):
    """`value` as printable text: control, format and bidi characters become visible escapes.

    A report is pasted by strangers, and what it holds reaches the reviewer's terminal. A
    field is escaped whole (`keep=""`), so it cannot forge a line of the review around it.
    """
    text = value if isinstance(value, str) else str(value)
    return "".join(ch if ch in keep or ch.isprintable() else ch.encode("unicode_escape").decode("ascii") for ch in text)


def review(report):
    """(ok, lines) -- the mechanical half of reviewing one submission."""
    lines = []
    try:
        evidence_report.validate(report)
    except evidence_report.InvalidReportError as exc:
        return False, ["REJECTED: %s" % _plain(exc, "")]

    agent = report["agent"]
    if agent not in EVIDENCE:
        return False, ["REJECTED: %s is not an agent this matrix has a row for" % _plain(repr(agent), "")]

    lines.append("report for %s: valid" % _plain(agent, ""))
    lines.append("  basis    %s (driver: %s)" % (_plain(report["basis"], ""), _plain(report["driver"], "")))
    lines.append("  version  %s" % _plain(report.get("version", "unrecorded"), ""))
    lines.append("  date     %s" % _plain(report["date"], ""))
    if report.get("reporter"):
        lines.append("  reporter %s" % _plain(report["reporter"], ""))

    delta = evidence_report.diff_against(EVIDENCE[agent], report)
    if not delta["changes"]:
        lines.append("\nno change: this report agrees with the row already recorded.")
        return True, lines

    lines.append("\nwould change:")
    for field, (old, new) in sorted(delta["changes"].items()):
        lines.append("  %-10s %s -> %s" % (field, _plain(repr(old), ""), _plain(repr(new), "")))

    if delta["weakens_basis"]:
        # The change least likely to be intentional and least likely to be spotted in a
        # diff: a documentation report landing on top of a row that was measured.
        lines.append(
            "\nWARNING: this would replace measured evidence with unmeasured. That is a "
            "downgrade, and is almost never what a submitter intends."
        )
    return True, lines


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("report", help="path to a report JSON file, or - for stdin")
    parser.add_argument("--diff", action="store_true", help="also print the proposed row")
    args = parser.parse_args(argv)

    try:
        report = _read(args.report)
    except (OSError, ValueError) as exc:
        print("could not read report: %s" % exc, file=sys.stderr)
        return 2

    ok, lines = review(report)
    print(_plain("\n".join(lines)))
    if ok and args.diff:
        print("\nproposed row:")
        print(json.dumps(evidence_report.to_evidence(report), indent=2, sort_keys=True))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
