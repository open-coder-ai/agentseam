"""agentseam CLI: inspect the matrix, wire hooks, audit a machine."""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap

from . import __version__, adapters
from . import install as install_mod
from . import instructions as instructions_mod
from . import packaging as packaging_mod
from . import permissions as permissions_mod
from .contract import EVENTS
from .matrix import MATRIX, enforcement_level


def _cmd_agents(args):
    for name in sorted(MATRIX):
        row = MATRIX[name]
        print("%-16s %-14s %s" % (name, row["tier"], row["config"] or "(no hook config)"))
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
        if row["tier"] == "unadapted":
            # Known agent, no hook adapter here. Asking install_mod about it would raise;
            # more importantly the useful answer is "instruction files only", not an error.
            print("%-16s no hook adapter — instruction files only" % name)
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
    skipped = 0
    for agent in targets:
        lvl = ", ".join("%s=%s" % (e, enforcement_level(agent, e)) for e in events)
        try:
            path = install_mod.install(agent, events, args.command, args.repo, matcher=args.matcher)
        except ValueError as exc:
            # install() raising is deliberate (an event it cannot wire must not be dropped
            # silently), but for `all` one agent's gap must not take down the eleven that
            # can be wired: both documented example commands crashed with a traceback and
            # wired NOTHING, because at least one of twelve agents lacks a hook for any
            # given event set. Mirror the permissions primitive instead -- do what can be
            # done, name what cannot, exit non-zero so CI still notices.
            print("skipped %-14s %s" % (agent, exc), file=sys.stderr)
            skipped += 1
            continue
        print("wired %-16s -> %s   [%s]" % (agent, path, lvl))
    return 1 if skipped else 0


def _cmd_uninstall(args):
    targets = sorted(adapters.ADAPTERS) if args.agent == "all" else [args.agent]
    for agent in targets:
        print("%-16s %s" % (agent, "removed" if install_mod.uninstall(agent, args.repo) else "nothing to remove"))
    return 0


def _cmd_instructions(args):
    if args.list:
        found = instructions_mod.discover(args.repo)
        if not found:
            print("no instruction files found")
            return 0
        for agent in sorted(found):
            print("%-16s %s" % (agent, ", ".join(found[agent])))
        return 0
    text = args.text if args.text is not None else sys.stdin.read()
    if not text.strip():
        print("nothing to write (pass --text or pipe text on stdin)", file=sys.stderr)
        return 2
    try:
        results = instructions_mod.write(text, args.agents, args.repo, dry_run=args.dry_run)
    except KeyError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    decided = instructions_mod.plan(args.agents, args.repo)
    for path in sorted(results):
        print("%-9s %s" % (results[path], path))
    if decided["covered"]:
        print("covered by %s: %s" % (instructions_mod.SHARED_FILE, ", ".join(decided["covered"])))
    return 0


def _parse_rule(spec):
    """`action:capability[:specifier]` -- e.g. `deny:shell:curl *`."""
    parts = spec.split(":", 2)
    if len(parts) < 2:
        raise argparse.ArgumentTypeError("rule must be action:capability[:specifier], got %r" % (spec,))
    action, capability = parts[0], parts[1]
    specifier = parts[2] if len(parts) == 3 else None
    try:
        return permissions_mod.Rule(action, capability, specifier)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc))


def _print_unrecorded(rows, label):
    """Render the agents we have nothing recorded for, wrapped so the reasons stay readable.

    Printed rather than omitted: an agent missing from the listing would read as one we do
    not know about, when in fact we know about it and have not established this part.
    """
    if not rows:
        return
    print("\nno %s recorded (named rather than omitted):" % label)
    width = max(len(name) for name in rows)
    for name in sorted(rows):
        body = textwrap.wrap(rows[name], 96 - width)
        print("  %-*s  %s" % (width, name, body[0] if body else ""))
        for line in body[1:]:
            print("  %-*s  %s" % (width, "", line))


def _cmd_permissions(args):
    """Show each agent's permission surface, or render a policy and report what it loses."""
    if not args.rule:
        for name in permissions_mod.agents():
            row = permissions_mod.capability(name)
            print("%-16s %-18s %s" % (name, row["shape"], permissions_mod.config_files(name)[0]["path"]))
            # One action per line: Codex's prefix_rule spellings run past a terminal width
            # when joined, and a wrapped key name is harder to read than three short rows.
            for action in ("allow", "ask", "deny"):
                print("%-16s   %-5s %s" % ("", action, row["actions"][action] or "(cannot express)"))
        _print_unrecorded(permissions_mod.UNRECORDED, "permission model")
        return 0

    rc = 0
    targets = args.agents or permissions_mod.agents()
    for name in targets:
        try:
            rendered = permissions_mod.plan(name, args.rule)
        except KeyError as exc:
            print("%s: %s" % (name, exc.args[0].split(": ", 1)[-1]))
            rc = 1
            continue
        body = rendered.fragment
        print("# %s -> %s" % (name, rendered.path))
        print(body if isinstance(body, str) else json.dumps(body, indent=2, sort_keys=True))
        for gap in rendered.unrepresentable:
            print("# unrepresentable: %r -- %s" % (gap.rule, gap.reason))
        if not rendered.complete:
            rc = 1
        print()
    # A non-zero exit is the useful answer in CI: it means at least one rule you wrote
    # would not have been enforced on at least one agent you ship to.
    return rc


def _cmd_packaging(args):
    """Show where each agent looks for skills, subagents and commands -- and what it shares."""
    for name in packaging_mod.agents():
        row = packaging_mod.layout(name)
        print("%-16s %s" % (name, row["unit"] or "no bundle format — parts are found by location"))
        for part in packaging_mod.PARTS:
            print("%-16s   %-9s %s" % ("", part, row["parts"][part] or "(no equivalent)"))
    _print_unrecorded(packaging_mod.UNRECORDED, "packaging format")

    print("\nwrite once, works for several:")
    for part in packaging_mod.PARTS:
        for template, names in sorted(packaging_mod.same_path_for(part).items()):
            if len(names) > 1:
                print("  %-9s %-26s %s" % (part, template, ", ".join(names)))
    for agent in sorted(packaging_mod.ALSO_READS):
        for part, folders in sorted(packaging_mod.also_reads(agent).items()):
            print("  %s also reads another agent's %s from: %s" % (agent, part, ", ".join(folders)))
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

    ins = sub.add_parser("instructions", help="write standing instructions to every agent's file")
    ins.add_argument("--text", help="instruction text; omit to read stdin")
    ins.add_argument("--agents", nargs="*", help="target agents (default: all)")
    ins.add_argument("--repo", default=".")
    ins.add_argument("--dry-run", action="store_true")
    ins.add_argument("--list", action="store_true", help="show what exists instead of writing")
    ins.set_defaults(fn=_cmd_instructions)

    perm = sub.add_parser("permissions", help="each agent's permission surface; render a policy into it")
    perm.add_argument("--rule", action="append", type=_parse_rule, metavar="ACTION:CAPABILITY[:SPEC]")
    perm.add_argument("--agents", nargs="*", help="target agents (default: all with a recorded model)")
    perm.set_defaults(fn=_cmd_permissions)

    pkg = sub.add_parser("packaging", help="where each agent looks for skills, subagents and commands")
    pkg.set_defaults(fn=_cmd_packaging)

    u = sub.add_parser("uninstall", help="remove only agentseam's entries")
    u.add_argument("agent", help="agent name, or 'all'")
    u.add_argument("--repo", default=".")
    u.set_defaults(fn=_cmd_uninstall)

    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
