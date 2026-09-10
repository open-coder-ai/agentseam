#!/usr/bin/env python3
"""The experiment harness's own standalone argparse CLI (`python3 tools/experiment.py ...`).

Split out of experiment.py purely to keep that module under the review budget (task 1,
armed wave 1) -- this is the argument-parsing frontend, not the harness itself. It calls
`experiment.run_trial` and friends the same way `agentseam probe` (cli.py) does, so the two
entry points share the one engine and can never quietly drift apart.
"""

from __future__ import annotations

import argparse
import json

from .. import contract
from . import experiment, experiment_probe, experiment_report, recorded_driver


def main(argv=None):
    """Argument parsing and dispatch for `python3 tools/experiment.py <list|run> ...`."""
    parser = argparse.ArgumentParser(description=experiment.__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list", help="the trials and what each measures")
    run = sub.add_parser("run", help="run trials against an agent")
    run.add_argument("--agent", required=True)
    run.add_argument("--trial", action="append", help="repeatable; default is all")
    run.add_argument(
        "--event",
        default=contract.PRE_TOOL,
        choices=experiment.EVENTS,
        help="which gate to wire the probe at (default: pre_tool)",
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

    args.driver = recorded_driver.resolve_driver(args.agent, args.driver, event=args.event, version=args.agent_version)
    if args.record:
        recorded_driver.check_record_args(parser, driver=args.driver, agent_version=args.agent_version)

    trials = args.trial or sorted(experiment_probe.BEHAVIOURS)
    keep = args.keep or args.record
    results = [
        experiment.run_trial(
            args.agent, t, event=args.event, driver=args.driver, keep=keep, agent_version=args.agent_version
        )
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
