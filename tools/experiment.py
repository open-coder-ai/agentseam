#!/usr/bin/env python3
"""Measure what an agent's hooks actually enforce, instead of asserting it.

tools/capture.py answers *what shape is the payload*. This answers the two questions the
README leads with and the matrix cannot currently evidence:

    does `deny` actually block, and what happens when the hook dies?

Each trial is one scripted gate around one harmless command in a throwaway directory. The
command appends to a sentinel file; how many times it did so is the measurement. No
dialect parsing, no log scraping, no ambiguity.

The observable differs by gate, and that difference is the measurement. At prompt_submit
and pre_tool a block means the action never happened, so the sentinel count is the answer.
At stop the agent has already acted, so a refusal cannot un-run anything: it sends the
agent round again, and the hook fires a second time. The re-fire is what is counted there.

    python3 tools/experiment.py list
    python3 tools/experiment.py run --agent claude_code
    python3 tools/experiment.py run --agent claude_code --event stop
    python3 tools/experiment.py run --agent claude_code --trial crash --keep

Absent --driver, this replays a recording (tools/recorded_driver.py) if one exists for the
agent, else falls back to tools/reference_agent.py -- the vendor's documentation, made
executable. Both need no credentials, so the whole harness runs in CI for free, and a
disagreement between either and the real agent is a finding.

SAFETY: this probe denies, crashes and stalls on purpose. Every trial runs in a fresh
temporary directory that this module creates and removes, with a config written only
inside it. It never touches a config a person works in -- that is what separates it from
`capture`, which is safe anywhere because it always allows.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)

import experiment_probe  # noqa: E402
import experiment_report  # noqa: E402
import recorded_driver  # noqa: E402
import reference_agent  # noqa: E402

from agentseam import adapters, contract  # noqa: E402
from agentseam.matrix_terms import FAIL_CLOSED, FAIL_OPEN  # noqa: E402

SENTINEL = "ACTION_RAN"
SENTINEL_ALT = "ACTION_RAN_TRANSFORMED"
# Appending, not overwriting: where a driver does repeat its turn, "how many times" carries
# information "whether" cannot, and neither needs anyone's dialect parsed. An agent refused
# at Stop need not repeat work it has already done, so the count is a secondary signal
# there -- see _blocked().
TRIGGER = "echo ok >> %s" % SENTINEL
TRIGGER_ALT = "echo ok >> %s" % SENTINEL_ALT

#: Canonical events an experiment can gate at. Each blocks differently, and the difference
#: is the measurement -- see _blocked().
EVENTS = (contract.PROMPT_SUBMIT, contract.PRE_TOOL, contract.STOP)

#: Trial -> (measured field, value when the action still ran, value when it did not).
#: Reading a result is therefore a table lookup, not a judgement call.
_MEANING = {
    "allow": ("baseline_ok", True, False),
    "deny": ("block", False, True),
    "crash": ("fail_mode", FAIL_OPEN, FAIL_CLOSED),
    "silence": ("silence_means", "allow", "refusal-or-error"),
    "timeout": ("timeout_fail_mode", FAIL_OPEN, FAIL_CLOSED),
    "unknown": ("unknown_verb_means", "allow", "refusal-or-error"),
}


def _write_config(adapter, workspace, probe_command, event):
    """Wire the probe into a config *inside the scratch workspace* and return its path."""
    config_path = os.path.join(workspace, adapter.CONFIG_PATH)
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    body = adapter.hook_config([event], probe_command)
    with open(config_path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=2)
    return config_path


def _count(workspace, name):
    path = os.path.join(workspace, name)
    if not os.path.exists(path):
        return 0
    with open(path, encoding="utf-8") as fh:
        return len([line for line in fh if line.strip()])


def _observe(workspace):
    return {"runs": _count(workspace, SENTINEL), "alt_runs": _count(workspace, SENTINEL_ALT)}


def _blocked(event, observed, invocations):
    """Whether the gate stopped what it gates -- which is a different fact per event.

    At prompt_submit and pre_tool a block means the action never happened. At stop it
    cannot mean that: the agent has already acted, and a refusal to finish only sends it
    round again. The observable there is the hook firing again.

    Reading a second sentinel run instead only works for a driver that mechanically repeats
    its whole turn. A real agent goes round, sees the work already done, and declines to
    redo it: Claude Code 2.1.263 refused at Stop re-fired the hook nine times while the
    sentinel stayed at one, and scored as unblocked. A repeat run stays a secondary signal,
    because the reference driver does produce one.
    """
    runs = observed["runs"] + observed["alt_runs"]
    if event == contract.STOP:
        return invocations > 1 or runs > 1
    return runs == 0


def _invocations(record_dir):
    path = os.path.join(record_dir, "invocations.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _classify(trial, event, observed, invocations):
    """What one trial measured, as a (field, value) pair plus a human reading.

    `invocations` is a count, not a flag: at the stop gate how many times the hook fired is
    itself the measurement (see _blocked), and zero still means it never fired at all.
    """
    if not invocations:
        return "hook_reached", False, "the hook never fired -- config path or format is wrong for this version"
    if trial == "transform":
        if observed["alt_runs"] and not observed["runs"]:
            return "transform", True, "the rewritten input is what ran"
        if observed["runs"] and not observed["alt_runs"]:
            return "transform", False, "the original input ran; the rewrite was ignored"
        if not observed["runs"] and not observed["alt_runs"]:
            # Not ambiguous: the rewrite was offered and nothing at all ran, which is a
            # rewrite refused or degraded into a block. Only both-ran is undecidable.
            return "transform", False, "nothing ran: the rewrite was refused or degraded to a block"
        return "transform", None, "ambiguous: %s" % observed

    blocked = _blocked(event, observed, invocations)
    field, when_ran, when_blocked = _MEANING[trial]
    if event == contract.STOP:
        reading = "the agent was made to continue" if blocked else "the agent finished"
    else:
        reading = "action did not run" if blocked else "action ran"
    if trial == "allow" and blocked:
        reading = "BROKEN: a permissive answer was treated as a refusal -- the dialect is wrong"
    return field, (when_blocked if blocked else when_ran), reading


def run_trial(
    agent, trial, *, event=contract.PRE_TOOL, driver="reference", keep=False, timeout=None, agent_version=None
):
    """One trial: a real workspace, or (driver="recorded") a frozen recording replayed."""
    if event not in EVENTS:
        raise ValueError("cannot gate at %r (have: %s)" % (event, ", ".join(EVENTS)))
    if driver == recorded_driver.DRIVER_NAME:
        return recorded_driver.run_trial(agent, trial, event=event, version=agent_version)
    adapter = adapters.get(agent)
    workspace = tempfile.mkdtemp(prefix="agentseam-exp-%s-%s-" % (agent, trial))
    record_dir = os.path.join(workspace, ".record")
    os.makedirs(record_dir)
    try:
        probe_path = os.path.join(workspace, "probe.py")
        with open(probe_path, "w", encoding="utf-8") as fh:
            fh.write(
                experiment_probe.render(
                    trial,
                    record_dir,
                    agent=agent,
                    src_dir=os.path.abspath(os.path.join(HERE, "..", "src")),
                    trigger_alt=TRIGGER_ALT,
                )
            )
        # Owner-only. The probe is always invoked as `<interpreter> <path>` (below), so it
        # never needs an execute bit, and nothing else on the machine needs to read it.
        os.chmod(probe_path, 0o600)
        probe_command = "%s %s" % (json.dumps(sys.executable), json.dumps(probe_path))
        config_path = _write_config(adapter, workspace, probe_command, event)

        undocumented = None
        if driver == "reference":
            try:
                outcome = reference_agent.run_turn(config_path, command=TRIGGER, cwd=workspace, timeout=timeout)
            except reference_agent.Undocumented as exc:
                # The reference refuses to invent behaviour the protocol does not specify.
                # That refusal IS the measurement: the vendor's documentation is silent
                # here, so only a real run can settle it.
                undocumented, outcome = str(exc), None
        else:
            outcome = _drive_real(driver, workspace)

        observed = _observe(workspace)
        invocations = _invocations(record_dir)
        if undocumented is not None:
            # Named for the `unknown` trial's own field (unknown_verb_means) rather than
            # the generic "documented", so the diff can compare it against a real agent's
            # reading of that same field -- documentation-silence vs an observed answer is
            # exactly the disagreement worth surfacing. Any other trial keeps the older,
            # purely diagnostic "documented" reading; nothing else currently reaches here.
            if trial == "unknown":
                field, value = _MEANING["unknown"][0], "undocumented"
            else:
                field, value = "documented", False
            reading = "protocol is silent: %s" % undocumented
        else:
            field, value, reading = _classify(trial, event, observed, len(invocations))
        return {
            "agent": agent,
            "trial": trial,
            "event": event,
            "driver": driver,
            "measured": {field: value},
            "reading": reading,
            "observed": observed,
            "hook_invocations": len(invocations),
            "outcome": outcome,
            "workspace": workspace if keep else None,
        }
    finally:
        if not keep:
            shutil.rmtree(workspace, ignore_errors=True)


def _drive_real(command, workspace):
    """Drive a real agent CLI in the scratch workspace.

    `command` is a shell command template containing {prompt}. Kept deliberately thin:
    every agent's headless invocation differs, and encoding those here would rot faster
    than the matrix does.
    """
    prompt = "Run this exact shell command and nothing else: %s" % TRIGGER
    filled = command.replace("{prompt}", json.dumps(prompt))
    proc = subprocess.run(  # noqa: S602
        filled, shell=True, cwd=workspace, capture_output=True, text=True, timeout=300
    )
    return {"returncode": proc.returncode, "stdout": proc.stdout[-2000:], "stderr": proc.stderr[-2000:]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the trials and what each measures")
    run = sub.add_parser("run", help="run trials against an agent")
    run.add_argument("--agent", required=True)
    run.add_argument("--trial", action="append", help="repeatable; default is all")
    run.add_argument(
        "--event", default=contract.PRE_TOOL, choices=EVENTS, help="which gate to wire the probe at (default: pre_tool)"
    )
    recorded_driver.add_cli_args(run)
    run.add_argument("--keep", action="store_true", help="leave the scratch workspace for inspection")
    run.add_argument("--json", action="store_true")
    run.add_argument("--report", action="store_true", help="emit a submittable evidence report")
    run.add_argument("--agent-version", help="the agent build these trials ran against")
    run.add_argument("--reporter", help="how you want crediting, e.g. @handle")
    args = parser.parse_args(argv)

    if args.cmd == "list":
        for name, what in sorted(experiment_probe.BEHAVIOURS.items()):
            print("%-10s %s" % (name, what))
        return 0

    args.driver = recorded_driver.resolve_driver(args.agent, args.driver)
    if args.record:
        recorded_driver.check_record_args(parser, driver=args.driver, agent_version=args.agent_version)

    trials = args.trial or sorted(experiment_probe.BEHAVIOURS)
    keep = args.keep or args.record
    results = [
        run_trial(args.agent, t, event=args.event, driver=args.driver, keep=keep, agent_version=args.agent_version)
        for t in trials
    ]
    if args.record:
        recorded_driver.finalize_record(args, results)
    if args.report:
        report = experiment_report.as_report(results, version=args.agent_version, reporter=args.reporter)
        print(json.dumps(report, indent=2))
        return 0
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    return experiment_report.render(results, agent=args.agent, event=args.event, driver=args.driver)


if __name__ == "__main__":
    raise SystemExit(main())
