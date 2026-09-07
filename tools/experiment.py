#!/usr/bin/env python3
"""Measure what an agent's hooks actually enforce, instead of asserting it.

tools/capture.py answers *what shape is the payload*. This answers the two questions the
README leads with and the matrix cannot currently evidence:

    does `deny` actually block, and what happens when the hook dies?

Each trial is one scripted gate around one harmless command in a throwaway directory. The
command writes a sentinel file; whether that file exists afterwards is the measurement.
No dialect parsing, no log scraping, no ambiguity -- the action either happened or it did
not.

    python3 tools/experiment.py list
    python3 tools/experiment.py run --agent claude_code
    python3 tools/experiment.py run --agent claude_code --trial crash --keep

The default driver is tools/reference_agent.py: the vendor's documentation, made
executable. It needs no credentials, so the whole harness runs in CI for free, and a
disagreement between it and the real agent is precisely a documentation bug.

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
import reference_agent  # noqa: E402

from agentseam import adapters, contract  # noqa: E402
from agentseam.matrix_terms import FAIL_CLOSED, FAIL_OPEN  # noqa: E402

SENTINEL = "ACTION_RAN"
SENTINEL_ALT = "ACTION_RAN_TRANSFORMED"
TRIGGER = "echo ok > %s" % SENTINEL
TRIGGER_ALT = "echo ok > %s" % SENTINEL_ALT

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


def _write_config(adapter, workspace, probe_command):
    """Wire the probe into a config *inside the scratch workspace* and return its path."""
    config_path = os.path.join(workspace, adapter.CONFIG_PATH)
    os.makedirs(os.path.dirname(config_path), exist_ok=True)
    body = adapter.hook_config([contract.PRE_TOOL], probe_command)
    with open(config_path, "w", encoding="utf-8") as fh:
        json.dump(body, fh, indent=2)
    return config_path


def _observe(workspace):
    return {
        "sentinel": os.path.exists(os.path.join(workspace, SENTINEL)),
        "sentinel_alt": os.path.exists(os.path.join(workspace, SENTINEL_ALT)),
    }


def _invocations(record_dir):
    path = os.path.join(record_dir, "invocations.jsonl")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _classify(trial, observed, invoked):
    """What one trial measured, as a (field, value) pair plus a human reading."""
    if not invoked:
        return "hook_reached", False, "the hook never fired -- config path or format is wrong for this version"
    ran = observed["sentinel"]
    if trial == "transform":
        if observed["sentinel_alt"] and not ran:
            return "transform", True, "the rewritten input is what ran"
        if ran and not observed["sentinel_alt"]:
            return "transform", False, "the original input ran; the rewrite was ignored"
        return "transform", None, "ambiguous: %s" % observed
    field, when_ran, when_blocked = _MEANING[trial]
    reading = "action ran" if ran else "action did not run"
    if trial == "allow" and not ran:
        reading = "BROKEN: a permissive answer blocked the action -- the dialect is wrong"
    return field, (when_ran if ran else when_blocked), reading


def run_trial(agent, trial, *, driver="reference", keep=False, timeout=None):
    """One trial, start to finish, in a workspace created and destroyed here."""
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
        os.chmod(probe_path, 0o755)  # noqa: S103 - scratch dir, removed at the end of this call
        config_path = _write_config(adapter, workspace, "%s %s" % (json.dumps(sys.executable), json.dumps(probe_path)))

        undocumented = None
        if driver == "reference":
            try:
                outcome = reference_agent.run_pre_tool(config_path, command=TRIGGER, cwd=workspace, timeout=timeout)
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
            field, value, reading = "documented", False, "protocol is silent: %s" % undocumented
        else:
            field, value, reading = _classify(trial, observed, bool(invocations))
        return {
            "agent": agent,
            "trial": trial,
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


#: Measured field -> the matrix key it corresponds to. Fields absent here are observations
#: the matrix has no cell for yet (`silence_means`, `unknown_verb_means`) -- which is
#: itself worth surfacing: they are behaviours agentseam relies on but does not record.
_ASSERTED_KEY = {"block": "block", "fail_mode": "fail_mode", "transform": "transform"}


def diff_against_matrix(results, event=contract.PRE_TOOL):
    """Measured vs asserted, per field. The point of the whole exercise.

    Agreement is not the interesting outcome -- it just means the row was right. A
    disagreement means either the matrix overclaims (a policy that silently fails) or
    underclaims (a capability being left on the table).
    """
    from agentseam import matrix

    cell = matrix.capability(results[0]["agent"], event)
    rows = []
    for r in results:
        (field, measured), = r["measured"].items()
        key = _ASSERTED_KEY.get(field)
        claimed = cell.get(key) if key else None
        rows.append(
            {
                "trial": r["trial"],
                "field": field,
                "measured": measured,
                "asserted": claimed,
                "status": (
                    "unrecorded"
                    if key is None
                    else "agrees"
                    if claimed == measured
                    else "DISAGREES"
                ),
            }
        )
    return rows


def as_report(results, *, version=None, reporter=None, notes=None, today=None):
    """A submittable evidence report from a set of trial results.

    The basis is derived from the driver, never chosen by the caller: a run against the
    reference is documentation and says so. evidence_report.validate() enforces the same
    rule independently, so a hand-edited report cannot claim more than it earned.
    """
    from datetime import date

    from agentseam import evidence_report

    driver = results[0]["driver"]
    measured = {}
    for r in results:
        measured.update(r["measured"])
    report = {
        "report_version": evidence_report.REPORT_VERSION,
        "agent": results[0]["agent"],
        "basis": "vendor-docs" if driver == evidence_report.REFERENCE_DRIVER else "live-run-partial",
        "date": (today or date.today()).isoformat(),
        "driver": "reference" if driver == evidence_report.REFERENCE_DRIVER else "real-agent",
        "experiments": measured,
        "platform": sys.platform,
    }
    for key, value in (("version", version), ("reporter", reporter), ("notes", notes)):
        if value:
            report[key] = value
    return evidence_report.validate(report)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the trials and what each measures")
    run = sub.add_parser("run", help="run trials against an agent")
    run.add_argument("--agent", required=True)
    run.add_argument("--trial", action="append", help="repeatable; default is all")
    run.add_argument("--driver", default="reference", help="'reference', or a shell template containing {prompt}")
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

    trials = args.trial or sorted(experiment_probe.BEHAVIOURS)
    results = [run_trial(args.agent, t, driver=args.driver, keep=args.keep) for t in trials]
    if args.report:
        print(json.dumps(as_report(results, version=args.agent_version, reporter=args.reporter), indent=2))
        return 0
    if args.json:
        print(json.dumps(results, indent=2))
        return 0
    print("agent: %s   driver: %s\n" % (args.agent, args.driver))
    print("%-10s %-20s %-14s %-14s %s" % ("trial", "field", "measured", "asserted", "status"))
    disagreements = 0
    for r, d in zip(results, diff_against_matrix(results)):
        disagreements += d["status"] == "DISAGREES"
        print(
            "%-10s %-20s %-14s %-14s %s"
            % (r["trial"], d["field"], str(d["measured"]), str(d["asserted"]), d["status"])
        )
    print()
    for r in results:
        print("  %-10s %s" % (r["trial"], r["reading"]))
    if disagreements:
        print("\n%d disagreement(s): the matrix and this agent do not match." % disagreements)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
