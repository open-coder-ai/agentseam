#!/usr/bin/env python3
"""Capture what an agent really sends, and check it against what agentseam claims.

Nine of ten adapters here were built from vendor documentation and have never had a real
payload put through them. Docs go stale and field names get misread, and nothing in this
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

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))
sys.path.insert(0, HERE)

import probe_source  # noqa: E402
from redact import keys_of  # noqa: E402

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


def cmd_install(args):
    os.makedirs(CAPTURE_DIR, exist_ok=True)
    path = _probe_path()
    with open(path, "w") as fh:
        fh.write(_probe_source())
    os.chmod(path, 0o755)

    mod = adapters.get(args.agent)
    events = sorted(mod.REVERSE_EVENT_MAP)
    # Quoted interpreter and probe path -- chock's fix for interpreters under paths with
    # spaces, shell-agnostic between POSIX shells and cmd.exe. The agent name rides as
    # argv so the report can attribute payloads without an env var nobody sets.
    command = '"%s" "%s" %s' % (sys.executable, path, args.agent)
    written = install_mod.install(args.agent, events, command, repo_root=args.repo, owner=OWNER)
    print("probe:  %s" % path)
    print("wired:  %s" % written)
    print("events: %s" % ", ".join(events))
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


def _capture_files():
    """Every capture file: the per-process shards, plus the legacy shared file.

    Sorted so a report is deterministic across runs.
    """
    if not os.path.isdir(CAPTURE_DIR):
        return []
    names = [n for n in os.listdir(CAPTURE_DIR) if n.startswith("captured.") and n.endswith(".jsonl")]
    return [os.path.join(CAPTURE_DIR, n) for n in sorted(names)]


def _load():
    """Records from every capture file, skipping any line that is not whole.

    A torn line is a fact about the capture, not a reason to lose the other 122 records. The
    count is left on `_load.torn` so the report can say how much it skipped, rather than
    quietly presenting a partial capture as a complete one.
    """
    rows, torn = [], 0
    for path in _capture_files():
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    torn += 1
    _load.torn = torn
    return rows


_load.torn = 0


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


def cmd_report(args):
    """Compare what arrived against what the adapter expects, and say which won."""
    rows = _load()
    if _load.torn:
        print("NOTE: skipped %d unreadable line(s) -- a record torn by concurrent writes." % _load.torn)
        print("      Captures taken after the per-process-shard fix should not produce these.\n")
    if not rows:
        print("Nothing captured yet in %s" % CAPTURE_DIR)
        print("If the agent ran and this is still empty, the hook did not fire -- which is")
        print("itself a finding worth reporting: the config path or format may be wrong.")
        return 1

    by_agent = {}
    for row in rows:
        by_agent.setdefault(row["agent"], []).append(row["payload"])

    print("# Live capture report\n")
    print("%d payload(s) across %d agent(s). All values are already redacted to shape.\n" % (len(rows), len(by_agent)))

    for agent in sorted(by_agent):
        payloads = by_agent[agent]
        print("## %s (%d payloads)\n" % (agent, len(payloads)))
        if agent == UNLABELLED:
            print(
                "NOT a second vendor: these are payloads whose probe ran without an agent\n"
                "argument, so nothing could be held against an adapter. The usual cause is a\n"
                "second config firing the same probe -- Cursor also loads Claude Code-format\n"
                "hooks, so a leftover .claude/settings.json entry makes every event fire twice,\n"
                "once labelled and once not. Run `capture.py conflicts` to see which configs\n"
                "in this repo carry our probe.\n"
            )
        elif agent not in adapters.ADAPTERS:
            print("No adapter for this agent yet -- the shapes below are the whole finding.\n")
        mod = adapters.ADAPTERS.get(agent)
        seen_events, unclaimed, unparsed = set(), 0, []
        for payload in payloads:
            if mod and not mod.claims(payload):
                unclaimed += 1
            if mod:
                try:
                    seen_events.add(mod.parse(payload).event)
                except Exception as exc:  # a real finding, not a crash to hide
                    unparsed.append("%s: %s" % (type(exc).__name__, exc))
            seen = payload.get("hook_event_name") or payload.get("hookEventName")
            if seen:
                seen_events.add("vendor:%s" % seen)

        vendor_seen = sorted(e[7:] for e in seen_events if str(e).startswith("vendor:"))
        canonical = sorted(e for e in seen_events if not str(e).startswith("vendor:"))
        print("- vendor events seen: %s" % (", ".join(vendor_seen) or "(none carried a name)"))
        print("- parsed to: %s" % (", ".join(canonical) or "(nothing)"))
        if mod:
            known = set(getattr(mod, "EVENT_MAP", {}))
            surprises = sorted(set(vendor_seen) - known)
            missing = sorted(known - set(vendor_seen))
            print("- **events we do not know about: %s**" % (", ".join(surprises) or "none"))
            print("- claimed by our adapter: %d/%d" % (len(payloads) - unclaimed, len(payloads)))
            if unparsed:
                print("- **parse failures: %s**" % "; ".join(sorted(set(unparsed))))
            if missing:
                print("- mapped but not observed (may just not have fired): %s" % ", ".join(missing))
        print("\nKey paths observed:\n")
        paths = sorted({p for payload in payloads for p in keys_of(payload)})
        print("```\n%s\n```\n" % "\n".join(paths))
    print("\nPaste this whole report back. Everything in it is shape only.")
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
        s.add_argument("--agent", required=True, choices=sorted(adapters.ADAPTERS))
        s.add_argument("--repo", default=".")
        s.set_defaults(fn=fn)
    sub.add_parser("report", help="compare captures against what we claim").set_defaults(fn=cmd_report)
    conflicts = sub.add_parser("conflicts", help="which configs here fire the probe")
    conflicts.add_argument("--repo", default=".")
    conflicts.set_defaults(fn=cmd_conflicts)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
