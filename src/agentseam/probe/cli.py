"""agentseam CLI glue for `agentseam probe` -- split out of cli.py (review-budget, T2).

Owns only the argparse wiring and the two dispatch functions; the measurement itself lives
in this package's other modules, so cli.py's `probe` verb and tools/experiment.py's own
standalone CLI both call the identical engine and can never quietly drift apart.
"""

from __future__ import annotations

import json

from . import experiment, experiment_probe, experiment_report, recorded_driver


def cmd_list(_args):
    """`agentseam probe list`: the trials and what each measures."""
    for name, what in sorted(experiment_probe.BEHAVIOURS.items()):
        print("%-10s %s" % (name, what))
    return 0


def cmd_run(args):
    """`agentseam probe run`: exercise one agent's hooks against a driver; table, or --report."""
    driver = recorded_driver.resolve_driver(args.agent, args.driver, event=args.event, version=args.agent_version)
    if args.record:
        # `args._parser` is the actual `run` subparser (stashed via set_defaults in
        # add_subparser below), so a bad --record invocation gets the identical error text
        # tools/experiment.py's own CLI gives -- one validation, not a second copy of it here.
        recorded_driver.check_record_args(args._parser, driver=driver, agent_version=args.agent_version)

    trials = args.trial or sorted(experiment_probe.BEHAVIOURS)
    keep = args.keep or args.record
    results = [
        experiment.run_trial(
            args.agent, t, event=args.event, driver=driver, keep=keep, agent_version=args.agent_version
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
    return experiment_report.render(results, agent=args.agent, event=args.event, driver=driver)


def add_subparser(sub, *, default_event):
    """Wire `probe list`/`probe run` onto `sub` -- agentseam.cli's own top-level subparsers."""
    pr = sub.add_parser("probe", help="measure what an agent's hooks actually enforce, against a driver")
    psub = pr.add_subparsers(dest="probe_cmd", required=True)
    psub.add_parser("list", help="the trials and what each measures").set_defaults(fn=cmd_list)

    run = psub.add_parser("run", help="run trials against --driver; a table, or --report for submission")
    run.add_argument("--agent", required=True)
    run.add_argument("--trial", action="append", help="repeatable; default is all")
    run.add_argument(
        "--event",
        default=default_event,
        choices=experiment.EVENTS,
        help="which gate to wire the probe at (default: pre_tool)",
    )
    recorded_driver.add_cli_args(run)
    run.add_argument("--keep", action="store_true", help="leave the scratch workspace for inspection")
    run.add_argument("--json", action="store_true")
    run.add_argument("--report", action="store_true", help="emit a submittable evidence report")
    run.add_argument("--agent-version", help="the agent build these trials ran against")
    run.add_argument("--reporter", help="how you want crediting, e.g. @handle")
    run.set_defaults(fn=cmd_run, _parser=run)
