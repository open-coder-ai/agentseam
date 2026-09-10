#!/usr/bin/env python3
"""CI gate: replay every committed recording and fail if any trial disagrees with the matrix.

Only the recorded driver runs here -- no vendor CLI, no network, no credentials -- so this
is the one probe check every PR and every push can run for free. It answers a narrower
question than tools/watch_versions.py: not "has the vendor moved since the evidence was
taken", but "does the matrix still agree with what was already witnessed, on this change,
right now". A `DISAGREES` row here means a change made a `recorded` claim untrue.

    python3 tools/probe_ci.py

Exits 1 on any disagreement, 0 otherwise -- but 0 is not the same as "clean": it also prints
how many trials were actually checked, because checking nothing and finding no disagreement
would otherwise read exactly like success (contract invariant 4, "silence is a measurement,
not a pass").
"""

from __future__ import annotations

import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from agentseam import recordings  # noqa: E402
from agentseam.probe import experiment, experiment_report  # noqa: E402


def check():
    """(checked, disagreements): checked is a trial count, never a boolean -- see the
    module docstring's invariant-4 note. `disagreements` is the full row, not just a count,
    so the caller can print exactly what claimed what."""
    checked = 0
    disagreements = []
    for agent in recordings.agents():
        version = recordings.latest_version(agent)
        body = recordings.load_recording(agent, version)
        for event, event_body in sorted((body.get("events") or {}).items()):
            trials = sorted(event_body.get("trials") or {})
            results = [
                experiment.run_trial(agent, trial, event=event, driver="recorded", agent_version=version)
                for trial in trials
            ]
            checked += len(results)
            for row in experiment_report.diff_against_matrix(results, event=event):
                print(
                    "%-14s %-10s %-10s %-20s measured=%-10s asserted=%-10s %s"
                    % (agent, event, row["trial"], row["field"], row["measured"], row["asserted"], row["status"])
                )
                if row["status"] == "DISAGREES":
                    disagreements.append((agent, event, row))
    return checked, disagreements


def main():
    checked, disagreements = check()
    print(
        "\n%d trial(s) checked across %d committed recording(s), %d disagreement(s)"
        % (checked, len(recordings.agents()), len(disagreements))
    )
    if not checked:
        print("no recordings are committed -- this is a measurement of nothing, not a pass")
    return 1 if disagreements else 0


if __name__ == "__main__":
    raise SystemExit(main())
