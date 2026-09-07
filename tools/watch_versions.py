#!/usr/bin/env python3
"""Notice when an agent moves out from under its evidence.

Re-verifying sixteen agents on a schedule is not affordable and never will be. Noticing
that one of them shipped a release is nearly free, and it is the same signal: evidence
only needs re-taking when the thing it describes has changed.

    python3 tools/watch_versions.py                 # human table, exit 1 on drift
    python3 tools/watch_versions.py --json          # machine-readable, for a workflow
    python3 tools/watch_versions.py --agent claude_code

Run it on a schedule against a public repo -- Linux, no licences, no agent installs, no
credentials -- and it opens the question "is cursor's row still true?" on the day cursor
ships, rather than the day a user's policy silently fails.

**A source that cannot be reached is reported as unreachable, never as "no drift".** That
distinction is the entire value of this file: a watcher that goes quiet when the network
breaks is worse than no watcher, because it converts silence into false assurance.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from agentseam import staleness  # noqa: E402
from agentseam._data import load  # noqa: E402
from agentseam.matrix_evidence import EVIDENCE  # noqa: E402

SOURCES = load("vendor-releases.json")
TIMEOUT_SECONDS = 20
USER_AGENT = "agentseam-version-watch"

UNREACHABLE = "unreachable"
NO_SOURCE = "no-source"


def _get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})  # noqa: S310
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8"))


def latest_version(source):
    """(version, error) for one release source. Exactly one of the two is None."""
    kind = (source or {}).get("kind")
    if not kind:
        return None, NO_SOURCE
    ident = source.get("id")
    try:
        if kind == "npm":
            return _get_json("https://registry.npmjs.org/%s/latest" % ident)["version"], None
        if kind == "pypi":
            return _get_json("https://pypi.org/pypi/%s/json" % ident)["info"]["version"], None
        if kind == "github_releases":
            tag = _get_json("https://api.github.com/repos/%s/releases/latest" % ident)["tag_name"]
            return tag.lstrip("v"), None
    except (urllib.error.URLError, OSError, KeyError, ValueError, TimeoutError) as exc:
        return None, "%s: %s" % (UNREACHABLE, type(exc).__name__)
    return None, "unknown source kind: %r" % (kind,)


def check(agents=None, today=None):
    """Every agent's evidence against its vendor's current release."""
    rows = []
    for agent in sorted(agents or EVIDENCE):
        evidence = EVIDENCE.get(agent, {})
        current, error = latest_version(SOURCES.get(agent))
        state = staleness.status(evidence, current_version=current, today=today)
        state.update({"agent": agent, "source_error": error})
        rows.append(state)
    return rows


def drifted(rows):
    """Rows whose agent has shipped since the evidence was taken."""
    return [r for r in rows if r["verdict"] == staleness.DRIFTED]


def issue_body(rows):
    """Markdown for the issue a scheduled run opens. Names the agent and what moved."""
    lines = ["The following rows describe an agent version that is no longer current.", ""]
    for r in drifted(rows):
        lines.append(
            "- **%s** — evidence taken against `%s` (%s days ago); `%s` is now published."
            % (r["agent"], r["recorded_version"], r["age_days"], r["current_version"])
        )
    lines += [
        "",
        "This does not mean the row is wrong. It means nothing in this repository can",
        "currently say whether it is still right. Re-run `tools/experiment.py` against the",
        "new version, or mark the row re-verified if the hook contract is unchanged.",
    ]
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agent", action="append", help="repeatable; default is every agent")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--issue-body", action="store_true", help="markdown for a drift issue")
    parser.add_argument("--fail-on-drift", action="store_true", default=True)
    parser.add_argument("--no-fail-on-drift", dest="fail_on_drift", action="store_false")
    args = parser.parse_args(argv)

    rows = check(args.agent)

    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    elif args.issue_body:
        print(issue_body(rows))
    else:
        print("%-16s %-11s %-12s %-12s %-9s %s" % ("agent", "verdict", "recorded", "current", "age", "note"))
        for r in rows:
            print(
                "%-16s %-11s %-12s %-12s %-9s %s"
                % (
                    r["agent"],
                    r["verdict"],
                    r["recorded_version"] or "-",
                    r["current_version"] or "-",
                    "-" if r["age_days"] is None else "%dd" % r["age_days"],
                    r["source_error"] or "",
                )
            )
        moved = drifted(rows)
        unreachable = [r for r in rows if (r["source_error"] or "").startswith(UNREACHABLE)]
        unusable = [r for r in rows if not r["version_comparable"]]
        print(
            "\n%d drifted, %d source(s) unreachable, %d row(s) whose recorded version is not a version"
            % (len(moved), len(unreachable), len(unusable))
        )
        if unusable:
            print("  no drift can ever be computed for: %s" % ", ".join(r["agent"] for r in unusable))

    return 1 if (args.fail_on_drift and drifted(rows)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
