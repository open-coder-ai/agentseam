#!/usr/bin/env python3
"""Replays a frozen recording instead of driving a real agent process.

tools/experiment.py answers "what did the vendor do" by launching a real process. This
answers the same question from a `data/recordings/<agent>@<version>.json` file instead --
the freeze the owner's witness cycle calls for: watch what the vendor was seen to do once,
then test against that freeze until the vendor ships again (tools/watch_versions.py is what
notices the ship).

A replayed trial hands the recording's own sentinel and hook-invocation counts to
`experiment._classify` -- the exact function a live run would have gone through -- so a
recorded result is not a shortcut that happens to agree with the harness, it is the harness,
minus the subprocess. `record()` is the other half: it is what `tools/experiment.py --record`
calls to freeze a real run's results into that same file. Reading a recording back, so the
package and its consumers agree on what one contains, lives in `agentseam.recordings`
instead -- recordings are data the installed, stdlib-only package reads; this module, the
writer and replay driver, is a dev-only tool.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from agentseam import recordings  # noqa: E402
from agentseam.evidence_report import RECORDED_DRIVER, REFERENCE_DRIVER  # noqa: E402

#: The driver name tools/experiment.py dispatches on.
DRIVER_NAME = RECORDED_DRIVER

#: Drivers `--record` refuses: neither ever ran a real agent, so neither can produce live
#: evidence -- the same rule evidence_report.py enforces for a submitted report.
NON_LIVE_DRIVERS = (REFERENCE_DRIVER, DRIVER_NAME)


class NoRecording(Exception):
    """No recording covers the (agent, version, event, trial) asked for."""


def has_recording(agent):
    return recordings.latest_version(agent) is not None


def add_cli_args(run_parser):
    """--driver and --record, added here since both concern only this module's behaviour."""
    run_parser.add_argument(
        "--driver",
        default=None,
        help="'reference', 'recorded', or a shell template containing {prompt}; "
        "default: 'recorded' if a recording exists for --agent, else 'reference'",
    )
    run_parser.add_argument(
        "--record", action="store_true", help="freeze this run into data/recordings/<agent>@<agent-version>.json"
    )


def resolve_driver(agent, driver):
    """`driver` if given, else 'recorded' when a recording exists for `agent`, else the
    reference. Centralised here so tools/experiment.py's CLI stays a thin dispatcher."""
    if driver is not None:
        return driver
    return DRIVER_NAME if has_recording(agent) else REFERENCE_DRIVER


def check_record_args(parser, *, driver, agent_version):
    """Exit via `parser.error` if `--record` cannot proceed with these arguments."""
    if driver in NON_LIVE_DRIVERS:
        parser.error("--record needs a real agent: %r cannot produce live evidence" % driver)
    if not agent_version:
        parser.error("--record requires --agent-version")


def finalize_record(args, results):
    """Write the recording from a completed `run` invocation's own parsed args and results,
    then clean up any workspace `--record` asked `run_trial` to keep only for this."""
    path = record(
        agent=args.agent,
        version=args.agent_version,
        event=args.event,
        results=results,
        platform=sys.platform,
        reporter=args.reporter,
    )
    print("recorded: %s" % path)
    if not args.keep:
        for r in results:
            if r["workspace"]:
                shutil.rmtree(r["workspace"], ignore_errors=True)
    return path


def _trial_data(agent, trial, event, version):
    body = recordings.load_recording(agent, version)
    if body is None:
        raise NoRecording("no recording for %s%s" % (agent, ("@" + version) if version else ""))
    event_body = (body.get("events") or {}).get(event)
    if event_body is None:
        raise NoRecording("%s@%s never recorded %s" % (agent, body["version"], event))
    trial_body = (event_body.get("trials") or {}).get(trial)
    if trial_body is None:
        raise NoRecording("%s@%s/%s never recorded the %r trial" % (agent, body["version"], event, trial))
    return body, trial_body


def run_trial(agent, trial, *, event, version=None):
    """One trial's result, replayed from a recording through the real classifier.

    Shaped exactly like experiment.run_trial's return value, so a caller cannot tell the
    difference except by `driver` and `outcome`. No process is launched: the recording
    already holds the sentinel counts and hook-invocation count a real run produced.
    """
    body, trial_body = _trial_data(agent, trial, event, version)
    import experiment  # local: experiment.py imports this module, so this stays lazy

    observed = dict(trial_body["observed"])
    invocations = trial_body["hook_invocations"]
    field, value, reading = experiment._classify(trial, event, observed, invocations)  # noqa: SLF001
    return {
        "agent": agent,
        "trial": trial,
        "event": event,
        "driver": DRIVER_NAME,
        "measured": {field: value},
        "reading": reading,
        "observed": observed,
        "hook_invocations": invocations,
        "outcome": {
            "recorded_version": body["version"],
            "recorded_date": body["date"],
            "recorded_events": tuple(sorted(body["events"])),
        },
        "workspace": None,
    }


def _invocation_records(result):
    workspace = result.get("workspace")
    if not workspace:
        return []
    record_path = os.path.join(workspace, ".record", "invocations.jsonl")
    if not os.path.exists(record_path):
        return []
    with open(record_path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def record(*, agent, version, event, results, platform, reporter=None, notes=None, today=None):
    """Freeze one event's trial results into data/recordings/<agent>@<version>.json.

    Appends to an existing recording for the same (agent, version) instead of overwriting
    it, so running every gate as separate invocations builds one file -- a partial
    recording is simply one whose `events` does not yet name every gate.
    """
    existing = recordings.load_recording(agent, version) or {
        "agent": agent,
        "version": version,
        "platform": platform,
        "date": (today or date.today()).isoformat(),
        "driver": "real-agent",
    }
    if reporter:
        existing["reporter"] = reporter
    if notes:
        existing["notes"] = notes
    existing.setdefault("events", {})

    trials, keys = {}, set()
    for result in results:
        trials[result["trial"]] = {
            "observed": dict(result["observed"]),
            "hook_invocations": result["hook_invocations"],
        }
        for invocation in _invocation_records(result):
            keys.update(invocation.get("keys") or ())
    existing["events"][event] = {"trials": trials, "payload_keys": sorted(keys)}

    path = recordings.path_for(agent, version)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(existing, fh, indent=2, sort_keys=True)
        fh.write("\n")
    return path
