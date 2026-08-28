#!/usr/bin/env python3
"""Capture what an agent really sends, and check it against what agentseam claims.

Ten of twelve adapters here were built from vendor documentation and have never had a
real payload put through them; Claude Code and Cursor are the two that have. Docs go stale and field names get misread, and nothing in this
repository would notice. This closes that.

    python3 tools/capture.py detect                 # which agents are on this machine
    python3 tools/capture.py install --agent cursor # wire a recording probe
    ... use the agent normally for a minute ...
    python3 tools/capture.py report                 # what we got right and wrong
    python3 tools/capture.py uninstall --agent cursor

The probe **always allows**. It records and gets out of the way, so it cannot interfere with
real work -- verification that costs you a broken session is not worth running.

Everything is redacted to shape before it is written, so `captured.jsonl` is already safe to
share. There is no second step to forget, and the file on disk never held the content.
"""

from __future__ import annotations

import argparse
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)

import probe_source  # noqa: E402

from agentseam import adapters  # noqa: E402
from agentseam import install as install_mod  # noqa: E402

CAPTURE_DIR = os.environ.get("AGENTSEAM_CAPTURE_DIR", os.path.join(HERE, "..", ".capture"))
CAPTURE_FILE = os.path.join(CAPTURE_DIR, "captured.jsonl")
OWNER = "agentseam-capture"

#: Where each agent keeps state, used only to guess what is installed. A miss here means
#: "not found in the usual place", never "you do not have it".
FOOTPRINTS = {
    "claude_code": ("~/.claude", ".claude"),
    "codex_cli": ("~/.codex", ".codex"),
    "cursor": ("~/.cursor", ".cursor"),
    "devin": ("~/.config/devin", ".devin"),
    "gemini_cli": ("~/.gemini", ".gemini"),
    "grok": ("~/.grok", ".grok"),
    "kimi_code": ("~/.kimi-code",),
    "antigravity": ("~/.gemini/antigravity", ".agents"),
    "vscode_copilot": ("~/.copilot", ".github/hooks"),
    "windsurf": ("~/.codeium/windsurf", ".windsurf"),
    "junie": ("~/.junie", ".junie"),
    "tabnine": ("~/.tabnine", ".tabnine"),
}


def _probe_source():
    """The probe program. Its text lives in probe_source.py -- a different activity."""
    return probe_source.render(HERE, CAPTURE_DIR)


def _probe_path():
    return os.path.join(CAPTURE_DIR, "probe.py")


def cmd_detect(args):
    """Guess which agents are on this machine, so the evening is spent on real ones."""
    print("Agents whose usual config location exists here:\n")
    found = []
    for agent in sorted(FOOTPRINTS):
        hits = [p for p in FOOTPRINTS[agent] if os.path.exists(os.path.expanduser(p))]
        if hits:
            found.append(agent)
            print("  %-16s %s" % (agent, ", ".join(hits)))
    if not found:
        print("  (none found -- this only checks the usual paths, so it can be wrong)")
    print("\nThis is a guess from paths, not proof. Run install for whichever you actually use.")
    return 0


def _probe_command(path, agent):
    """The probe invocation, spelled so every shell an agent might wrap it in will RUN it.

    The quoted form -- `"C:\\py.exe" "probe.py" agent` -- is correct for POSIX shells and
    cmd.exe, and was chosen for interpreters under paths with spaces. PowerShell is the gap
    it did not cover: there, a line BEGINNING with a quoted path parses as a string
    expression rather than an invocation, so nothing runs at all. Two vendors are now known
    to wrap hooks that way on Windows -- Codex, and VS Code Copilot via hookExecutor.ts's
    getShellCommand -- and both were silently recording nothing.

    Those two have per-platform override fields in their own config schema and use them. The
    other ten have no such field recorded, so the only lever left is this string. An
    UNQUOTED interpreter path parses in command mode in all three shells, and needs no
    vendor support -- so it is used whenever the path has no spaces, which is the common
    case. A path with spaces still needs the quotes, and there is no single string that
    works everywhere; install() warns rather than silently choosing one shell.

    Safe here in a way it would not be in a real guard: this probe always allows. An
    invocation that fails to resolve costs a capture, not a gate.
    """
    interpreter = sys.executable
    if " " not in interpreter:
        return '%s "%s" %s' % (interpreter, path, agent)
    return '"%s" "%s" %s' % (interpreter, path, agent)


def _detected_agents():
    return sorted(a for a in FOOTPRINTS if any(os.path.exists(os.path.expanduser(p)) for p in FOOTPRINTS[a]))


def cmd_install(args):
    """Wire the probe. `--agent detected` does every agent whose config location exists.

    Wiring several at once is deliberate for a capture evening: the probe always allows, so
    the cost of an extra one is a few recorded payloads, and the benefit is that whichever
    agent you happen to open is already recording. It also makes double-firing visible --
    that is how Cursor was found to load Claude Code's config as well as its own, with every
    event arriving twice.
    """
    if args.agent == "detected":
        found = _detected_agents()
        if not found:
            print("no agent config locations found here; name one explicitly with --agent")
            return 1
        print("wiring %d detected agent(s): %s\n" % (len(found), ", ".join(found)))
        rc = 0
        for agent in found:
            rc |= cmd_install(argparse.Namespace(agent=agent, repo=args.repo))
            print()
        return rc
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    path = _probe_path()
    with open(path, "w") as fh:
        fh.write(_probe_source())
    os.chmod(path, 0o755)

    mod = adapters.get(args.agent)
    events = sorted(mod.REVERSE_EVENT_MAP)
    command = _probe_command(path, args.agent)
    written = install_mod.install(args.agent, events, command, repo_root=args.repo, owner=OWNER)
    print("probe:  %s" % path)
    print("wired:  %s" % written)
    print("events: %s" % ", ".join(events))
    # A module that imports powershell_command emits a per-platform override, so a quoted
    # command is safe there; the rest have only the one string.
    if " " in sys.executable and not hasattr(mod, "powershell_command"):
        print(
            "\nWARNING: your interpreter path contains spaces, so the command must stay quoted --\n"
            "         and %s records no per-platform override field. If this agent wraps hooks in\n"
            "         PowerShell on Windows, the hook will not run. Check the capture is non-empty." % args.agent
        )
    others = [a for a in _installed_configs(args.repo) if a != args.agent]
    if others:
        print("\nWARNING: these configs in this repo also fire the probe: %s" % ", ".join(others))
        print("Agents read each other's config files, so one action can fire the probe twice")
        print("and half the records will be labelled '?'. Uninstall them first.")
    print("\nNow use %s normally for a minute -- open it, have it read a file, run a command," % args.agent)
    print("write something, end the session. Then: python3 tools/capture.py report")
    return 0


def cmd_uninstall(args):
    removed = install_mod.uninstall(args.agent, args.repo, owner=OWNER)
    print("%s: %s" % (args.agent, "probe removed" if removed else "nothing of ours was there"))
    return 0


UNLABELLED = "?"


def _installed_configs(repo_root):
    """Every agent whose config in this repo currently carries our probe."""
    return [agent for agent in sorted(adapters.ADAPTERS) if install_mod.installed(agent, repo_root, owner=OWNER)]


def cmd_conflicts(args):
    """Say which configs fire our probe, and warn when more than one will.

    Agents read each other's config files -- Cursor loads Claude Code-format hooks, VS Code
    reads several of Claude Code's folders. Two installs in one repo therefore means the same
    hook fires twice for one action, and the payloads split across two labels for no reason a
    reader could guess.
    """
    found = _installed_configs(args.repo)
    if not found:
        print("No agentseam capture probe is installed in %s" % os.path.abspath(args.repo))
        return 0
    for agent in found:
        print("  %-16s %s" % (agent, install_mod.config_path(agent, args.repo)))
    if len(found) > 1:
        print("\nMore than one config here fires the probe. Agents read each other's files")
        print("(Cursor loads Claude Code-format hooks), so one action can fire it twice --")
        print("which is what produces payloads labelled '?' alongside labelled ones.")
        print("Uninstall the ones you are not verifying: python3 tools/capture.py uninstall --agent <name>")
        return 1
    return 0


def main(argv=None):
    import argparse

    p = argparse.ArgumentParser(prog="capture", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("detect", help="guess which agents are installed here").set_defaults(fn=cmd_detect)
    for name, fn, helptext in (
        ("install", cmd_install, "wire the recording probe for one agent"),
        ("uninstall", cmd_uninstall, "remove the probe"),
    ):
        s = sub.add_parser(name, help=helptext)
        # "detected" wires every agent whose config location exists here, so one evening
        # yields payloads from whichever the user actually opens rather than one guess.
        s.add_argument("--agent", required=True, choices=sorted(adapters.ADAPTERS) + ["detected"])
        s.add_argument("--repo", default=".")
        s.set_defaults(fn=fn)
    sub.add_parser("report", help="compare captures against what we claim").set_defaults(fn=cmd_report)
    conflicts = sub.add_parser("conflicts", help="which configs here fire the probe")
    conflicts.add_argument("--repo", default=".")
    conflicts.set_defaults(fn=cmd_conflicts)
    args = p.parse_args(argv)
    return args.fn(args)


# Re-exported: tests and callers address the report through `capture`, and keeping that
# address stable is cheaper than teaching every caller about the split. Imported here, after
# every name in this module is bound, so capture_report's lazy `from capture import ...`
# (inside its own functions) always finds a fully-initialized module -- but still before
# __main__ runs main(), which needs cmd_report bound to build the "report" subcommand.
from capture_report import _capture_files, _load, _versions_in, cmd_report  # noqa: E402,F401

if __name__ == "__main__":
    sys.exit(main())
