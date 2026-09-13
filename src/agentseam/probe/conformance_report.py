"""Cross-vendor conformance over the committed recordings: where a witnessed run lands.

Each new witnessed run has been worth something only in the abstract -- one more row moving
off vendor-docs. This is the concrete thing it buys: with two agents recorded at the same
gate, every trial becomes a comparison, and `conformance.classify` says whether a difference
is a true vendor property or this layer leaking a dialect.

Deliberately honest about the current state rather than impressive. One agent is recorded, so
every comparison here reports `undecidable` -- one vendor cannot differ from anything. That
reads as an empty result and is the correct one; the moment a second recording lands the same
command starts answering. Nothing is fabricated to fill the table in the meantime.

Replay, not launch: `recorded_driver.run_trial` runs each recorded trial back through the real
classifier without starting a process, so this is free to run in CI and measures exactly what
a live run measured.
"""

from __future__ import annotations

from .. import conformance, recordings
from . import recorded_driver


def _measured(agent, trial, event):
    """The one value `agent`'s recording measured for `trial` at `event`, or None."""
    try:
        result = recorded_driver.run_trial(agent, trial, event=event)
    except recorded_driver.NoRecording:
        return None
    measured = result.get("measured") or {}
    return next(iter(measured.values()), None) if measured else None


def events_recorded():
    """Every gate at least one recording covers, sorted."""
    found = set()
    for agent in recordings.agents():
        body = recordings.load_recording(agent) or {}
        found.update(body.get("events") or {})
    return sorted(found)


def trials_recorded(event):
    """Every trial at least one recording covers at `event`, sorted."""
    found = set()
    for agent in recordings.agents():
        body = recordings.load_recording(agent) or {}
        found.update(((body.get("events") or {}).get(event) or {}).get("trials") or {})
    return sorted(found)


def compare(event):
    """One row per trial at `event`: the per-agent verdicts and what their difference means."""
    rows = []
    for trial in trials_recorded(event):
        verdicts = {}
        for agent in recordings.agents():
            value = _measured(agent, trial, event)
            if value is not None:
                verdicts[agent] = value
        if not verdicts:
            continue
        rows.append({"trial": trial, "verdicts": verdicts, "result": conformance.classify(verdicts, event)})
    return rows


def gaps(event=None):
    """Every comparison that condemns the seam. Empty is the answer a green CI gate wants."""
    events = [event] if event else events_recorded()
    return [
        {"event": ev, **row} for ev in events for row in compare(ev) if row["result"]["call"] == conformance.SEAM_GAP
    ]


def render(event=None):
    """Print the comparison and return an exit code: non-zero only for a seam gap."""
    witnessed = recordings.agents()
    print("recorded agents: %s" % (", ".join(witnessed) or "(none)"))
    if len(witnessed) < 2:  # noqa: PLR2004 -- conformance._MIN_VENDORS, stated where it is read
        print(
            "a comparison needs two: with %d recorded, every trial below reads undecidable, which\n"
            "is the honest answer rather than an empty one. Witness a second agent at the same gate\n"
            "and these rows start deciding." % len(witnessed)
        )
    events = [event] if event else events_recorded()
    found = 0
    for ev in events:
        rows = compare(ev)
        if not rows:
            continue
        print("\n%s" % ev)
        for row in rows:
            verdicts = ", ".join("%s=%s" % (a, v) for a, v in sorted(row["verdicts"].items()))
            print("  %-10s %-12s %s" % (row["trial"], row["result"]["call"], verdicts))
            if row["result"]["call"] == conformance.SEAM_GAP:
                found += 1
                print("             %s" % row["result"]["reason"])
    if found:
        print("\n%d seam gap(s): vendors the matrix says are equally able measured differently." % found)
        return 1
    return 0
