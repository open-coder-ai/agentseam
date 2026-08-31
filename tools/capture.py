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
    """The probe invocation, spelled so every shell an agent might wrap it in will RUN it."""
    interpreter = sys.executable
    if " " not in interpreter:
        return '%s "%s" %s' % (interpreter, path, agent)
    return '"%s" "%s" %s' % (interpreter, path, agent)


def _detected_agents():
    return sorted(a for a in FOOTPRINTS if any(os.path.exists(os.path.expanduser(p)) for p in FOOTPRINTS[a]))


def cmd_install(args):
    """Wire the probe. `--agent detected` does every agent whose config location exists."""
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
    written = install_mod.install(args.agent, events, command, repo_root=args.repo, owner=OWNER, fail_closed=False)
    print("probe:  %s" % path)
    print("wired:  %s" % written)
    print("events: %s" % ", ".join(events))
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
    """Say which configs fire our probe, and warn when more than one will."""
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
        s.add_argument("--agent", required=True, choices=sorted(adapters.ADAPTERS) + ["detected"])
        s.add_argument("--repo", default=".")
        s.set_defaults(fn=fn)
    sub.add_parser("report", help="compare captures against what we claim").set_defaults(fn=cmd_report)
    conflicts = sub.add_parser("conflicts", help="which configs here fire the probe")
    conflicts.add_argument("--repo", default=".")
    conflicts.set_defaults(fn=cmd_conflicts)
    args = p.parse_args(argv)
    return args.fn(args)


from capture_report import _capture_files, _load, _versions_in, cmd_report  # noqa: E402,F401

if __name__ == "__main__":
    sys.exit(main())
