"""The capture report: compare what arrived against what the adapters claim.

Split from capture.py because reading a capture back and judging it is a different activity
from installing the probe that produced it -- and because capture.py crossed the 300-line
review budget, where the remedy is splitting by activity rather than raising the number.

Imports its constants from capture so there is exactly one definition of where captures
live; capture re-exports the entry point so the CLI surface is unchanged.
"""

from __future__ import annotations

import json
import os

from redact import keys_of

from agentseam import adapters


def _capture_files():
    """Every capture file: the per-process shards, plus the legacy shared file.

    Sorted so a report is deterministic across runs. `capture` is imported lazily here and
    in cmd_report -- report needs capture's constants, capture re-exports report's entry
    point, and the lazy direction is the one free of a load-order-sensitive cycle.
    """
    from capture import CAPTURE_DIR

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


def _versions_in(value):
    """Version strings the capture kept, wherever they are nested.

    Redaction already allows these through -- `cursor_version` is on the structural
    allowlist and `1.5.11` is enum-like -- but the report only ever printed key *paths*, so
    the one fact the matrix requires for a `verified` record was sitting in the file
    unread, and had to be asked for by hand.
    """
    found = []
    if isinstance(value, dict):
        for key, sub in value.items():
            if "version" in key.lower() and isinstance(sub, str) and not sub.startswith("<"):
                found.append(sub)
            else:
                found.extend(_versions_in(sub))
    elif isinstance(value, list):
        for sub in value:
            found.extend(_versions_in(sub))
    return found


def cmd_report(args):
    """Compare what arrived against what the adapter expects, and say which won."""
    from capture import CAPTURE_DIR, UNLABELLED

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
        versions = sorted({str(v) for payload in payloads for v in _versions_in(payload)})
        if versions:
            print("- **agent version: %s**" % ", ".join(versions))
        # Keys grouped per vendor event, not unioned across the session. A union cannot
        # say which event carries which key, and that ambiguity blocked four follow-ups
        # from one live run: nobody could tell whether tool_output exists on failures, or
        # which events carry session_id, without another capture. The data was on disk the
        # whole time -- one record per payload, hook_event_name preserved by redaction.
        print("\nKey paths observed, per event:\n```")
        by_event = {}
        for payload in payloads:
            name = payload.get("hook_event_name") or payload.get("hookEventName") or "(unnamed)"
            by_event.setdefault(name, set()).update(keys_of(payload))
        for name in sorted(by_event):
            print("%s:" % name)
            for path in sorted(by_event[name]):
                print("  %s" % path)
        print("```\n")
    print("\nPaste this whole report back. Everything in it is shape only.")
    return 0


_load.torn = 0
