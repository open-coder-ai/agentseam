"""agentseam CLI: inspect the matrix, wire hooks, audit a machine."""

from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__, adapters
from . import install as install_mod
from .contract import EVENTS
from .matrix import MATRIX, enforcement_level


def _cmd_agents(args):
    for name in sorted(MATRIX):
        row = MATRIX[name]
        print("%-16s %-14s %s" % (name, row["tier"], row["config"] or "(no hook surface)"))
    return 0


def _cmd_matrix(args):
    if args.json:
        print(json.dumps(MATRIX, indent=2, sort_keys=True))
        return 0
    events = [e for e in EVENTS if any(e in r["events"] for r in MATRIX.values())]
    width = max(len(e) for e in events)
    header = " " * (width + 2) + "  ".join("%-14s" % a for a in sorted(MATRIX))
    print(header)
    for ev in events:
        cells = "  ".join("%-14s" % enforcement_level(a, ev) for a in sorted(MATRIX))
        print("%-*s  %s" % (width, ev, cells))
    return 0


def _cmd_doctor(args):
    """Report what is actually wired here, and how stale each capability claim is."""
    from datetime import date

    today = date.today()
    rc = 0
    for name in sorted(MATRIX):
        row = MATRIX[name]
        if row["tier"] == "none":
            print("%-16s no hook surface — %s" % (name, row["notes"].split(".")[0]))
            continue
        wired = install_mod.installed(name, args.repo)
        verified = row["verified"]
        try:
            y, m, d = (int(x) for x in verified["date"].split("-"))
            age = (today - date(y, m, d)).days
        except (ValueError, KeyError):
            age = None
        stale = " STALE" if age is not None and age > 90 else ""
        if stale:
            rc = 1
        print(
            "%-16s wired=%-5s verified=%s (%s days ago)%s"
            % (name, "yes" if wired else "no", verified["date"], age if age is not None else "?", stale)
        )
    return rc


def _cmd_install(args):
    events = args.events or ["pre_tool"]
    unknown = [e for e in events if e not in EVENTS]
    if unknown:
        print("unknown event(s): %s" % ", ".join(unknown), file=sys.stderr)
        return 2
    targets = sorted(adapters.ADAPTERS) if args.agent == "all" else [args.agent]
    for agent in targets:
        lvl = ", ".join("%s=%s" % (e, enforcement_level(agent, e)) for e in events)
        path = install_mod.install(agent, events, args.command, args.repo, matcher=args.matcher)
        print("wired %-16s -> %s   [%s]" % (agent, path, lvl))
    return 0


def _cmd_uninstall(args):
    targets = sorted(adapters.ADAPTERS) if args.agent == "all" else [args.agent]
    for agent in targets:
        print("%-16s %s" % (agent, "removed" if install_mod.uninstall(agent, args.repo) else "nothing to remove"))
    return 0


def main(argv=None):
    # A CLI that dies on `| head` is a broken CLI: SIGPIPE arrives as BrokenPipeError
    # in Python, and the interpreter also complains at shutdown unless stdout is
    # redirected away from the closed pipe.
    try:
        return _main(argv)
    except BrokenPipeError:
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except OSError:
            pass
        return 0
    except KeyboardInterrupt:
        return 130


def _main(argv=None):
    p = argparse.ArgumentParser(prog="agentseam", description=__doc__)
    p.add_argument("--version", action="version", version=__version__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("agents", help="list known agents").set_defaults(fn=_cmd_agents)

    m = sub.add_parser("matrix", help="what each agent can enforce, per event")
    m.add_argument("--json", action="store_true")
    m.set_defaults(fn=_cmd_matrix)

    d = sub.add_parser("doctor", help="what is wired here; flag stale capability claims")
    d.add_argument("--repo", default=".")
    d.set_defaults(fn=_cmd_doctor)

    i = sub.add_parser("install", help="wire a handler command into an agent's config")
    i.add_argument("agent", help="agent name, or 'all'")
    i.add_argument("command", help="command the agent should run for each event")
    i.add_argument("--events", nargs="*", help="canonical events (default: pre_tool)")
    i.add_argument("--matcher", help="vendor tool matcher, e.g. 'Write|Edit'")
    i.add_argument("--repo", default=".")
    i.set_defaults(fn=_cmd_install)

    u = sub.add_parser("uninstall", help="remove only agentseam's entries")
    u.add_argument("agent", help="agent name, or 'all'")
    u.add_argument("--repo", default=".")
    u.set_defaults(fn=_cmd_uninstall)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
