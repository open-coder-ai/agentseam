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
import subprocess
import sys
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "src"))

from agentseam import recordings, staleness  # noqa: E402
from agentseam._data import load  # noqa: E402
from agentseam.contract import PRE_TOOL, PROMPT_SUBMIT, STOP  # noqa: E402
from agentseam.matrix_data import MATRIX  # noqa: E402
from agentseam.matrix_evidence import EVIDENCE, claim_record  # noqa: E402
from agentseam.matrix_terms import CLAIM_FAIL_MODE  # noqa: E402

#: gh CLI labels a drift issue always carries. Created with --force if the repo lacks them.
ISSUE_LABELS = ("evidence", "help wanted")
_LABEL_COLORS = {"evidence": "0e8a16", "help wanted": "128a0c"}

#: Gates tools/experiment.py can actually wire a probe at (mirrors its own EVENTS) -- a
#: drift issue must never suggest re-witnessing a gate the kit cannot even gate at.
EXPERIMENTABLE_EVENTS = (PROMPT_SUBMIT, PRE_TOOL, STOP)

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


def _event_versions(agent):
    """(event, record) for every event this agent's row claims. A gate a committed
    recording covers compares against *that* recording's version -- the frozen artifact is
    now the ground truth for it, ahead of the per-claim override it otherwise falls back to
    (task 4), which itself falls back to the row's own record."""
    row = MATRIX.get(agent) or {}
    body = recordings.load_recording(agent)
    covered = set((body or {}).get("events") or ())
    out = []
    for event in row.get("events", {}):
        if event in covered:
            out.append((event, {"basis": "live-run", "version": body["version"], "date": body["date"]}))
            continue
        record = claim_record(row, event, CLAIM_FAIL_MODE)
        out.append((event, record if record.get("version") else EVIDENCE.get(agent, {})))
    return out


def check(agents=None, today=None):
    """Every agent's evidence against its vendor's current release.

    One row per agent, unless a per-claim record names a version the row's own does not --
    then one row per event, so an event witnessed more recently than its row (task 4) reads
    FRESH while the rest of that same row still reads its own, possibly older, drift.
    """
    rows = []
    for agent in sorted(agents or EVIDENCE):
        current, error = latest_version(SOURCES.get(agent))
        per_event = _event_versions(agent)
        if len({record.get("version") for _, record in per_event}) <= 1:
            state = staleness.status(EVIDENCE.get(agent, {}), current_version=current, today=today)
            state.update({"agent": agent, "event": None, "source_error": error})
            rows.append(state)
            continue
        for event, record in per_event:
            state = staleness.status(record, current_version=current, today=today)
            state.update({"agent": agent, "event": event, "source_error": error})
            rows.append(state)
    return rows


def drifted(rows):
    """Rows whose agent has shipped since the evidence was taken."""
    return [r for r in rows if r["verdict"] == staleness.DRIFTED]


def _label(r):
    """`agent`, or `agent/event` for a row split out because one event's own evidence
    names a different version than the rest of its row (task 4)."""
    return r["agent"] if r["event"] is None else "%s/%s" % (r["agent"], r["event"])


def issue_title(agent, current_version):
    """The exact title a drift issue carries -- also the key `open_issues` searches by to
    decide whether one is already open, so this is the one place that spelling lives."""
    return "evidence: %s %s — re-witness wanted" % (agent, current_version)


def agents_needing_issues(rows):
    """Drifted agents, each with its own row(s) -- one issue per agent, not per row."""
    by_agent = {}
    for r in drifted(rows):
        by_agent.setdefault(r["agent"], []).append(r)
    return dict(sorted(by_agent.items()))


def issue_body_for_agent(agent, agent_rows):
    """Self-sufficient markdown for one drifted agent: what moved, the exact commands to
    re-witness it, and both ways to submit the result.

    A drift issue is a work order for whoever has `agent` installed, not a note to the
    maintainer (owner decision 2026-09-07, org-plan plan/agentseam-project.md 'Evidence
    layer') -- so this owes the reader everything, not a pointer to CONTRIBUTING.md.
    """
    current = agent_rows[0]["current_version"]
    moved = "\n".join(
        "- `%s`: evidence taken against `%s` (%s days ago); `%s` is now published."
        % (r["event"] or agent, r["recorded_version"], r["age_days"], r["current_version"])
        for r in agent_rows
    )
    row_events = set((MATRIX.get(agent) or {}).get("events") or {})
    events = sorted(row_events & set(EXPERIMENTABLE_EVENTS)) or [PRE_TOOL]
    # One invocation per gate, not one command with a repeated --event: the CLI takes a
    # single --event, and --record appending to the same file is what makes that build one
    # recording covering every gate rather than a race to overwrite it.
    per_event_commands = "\n".join(
        "python3 tools/experiment.py run --agent %s --event %s \\\n"
        '    --driver "<your headless CLI invocation, containing {prompt}>" \\\n'
        "    --agent-version %s --record --reporter @yourhandle" % (agent, event, current)
        for event in events
    )
    return "\n".join(
        [
            "`%s` has moved since its evidence was taken:" % agent,
            "",
            moved,
            "",
            "## Re-witness it",
            "",
            "You need `%s` installed and runnable headlessly from a terminal." % agent,
            "",
            "```bash",
            "pip install agentseam",
            per_event_commands,
            "```",
            "",
            "This writes `data/recordings/%s@%s.json` and touches nothing else on your machine." % (agent, current),
            "",
            "**A run against the `reference` or `recorded` driver never counts as a re-witness** --",
            "only a real, running `%s` does." % agent,
            "",
            "## Submit it",
            "",
            "- **Preferred**: open a PR adding that recording file plus the updated",
            "  `data/matrix.json` per-claim `test` pointers (see any recorded row for the shape).",
            '- **Or**: open an "Evidence report" issue and paste the recording JSON for a',
            "  maintainer to land.",
        ]
    )


def _ensure_labels():
    for label in ISSUE_LABELS:
        subprocess.run(  # noqa: S603, S607
            ["gh", "label", "create", label, "--color", _LABEL_COLORS[label], "--force"],
            check=False,
            capture_output=True,
            text=True,
        )


def _open_issue_titles():
    result = subprocess.run(  # noqa: S603, S607
        ["gh", "issue", "list", "--state", "open", "--limit", "200", "--json", "title"],
        check=True,
        capture_output=True,
        text=True,
    )
    return {row["title"] for row in json.loads(result.stdout)}


def open_issues(rows):
    """Open one GitHub issue per drifted agent lacking one already open. Returns the titles
    created, so a caller (or a test) can see exactly what happened without re-querying gh."""
    _ensure_labels()
    existing = _open_issue_titles()
    created = []
    for agent, agent_rows in agents_needing_issues(rows).items():
        title = issue_title(agent, agent_rows[0]["current_version"])
        if title in existing:
            continue
        command = ["gh", "issue", "create", "--title", title, "--body", issue_body_for_agent(agent, agent_rows)]
        for label in ISSUE_LABELS:
            command += ["--label", label]
        subprocess.run(command, check=True)  # noqa: S603
        created.append(title)
    return created


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agent", action="append", help="repeatable; default is every agent")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--issue-body", action="store_true", help="markdown for a drift issue, one per drifted agent")
    parser.add_argument(
        "--open-issues", action="store_true", help="open one GitHub issue per drifted agent via gh (needs GH_TOKEN)"
    )
    parser.add_argument("--fail-on-drift", action="store_true", default=True)
    parser.add_argument("--no-fail-on-drift", dest="fail_on_drift", action="store_false")
    args = parser.parse_args(argv)

    rows = check(args.agent)

    if args.open_issues:
        for title in open_issues(rows):
            print("opened: %s" % title)
        return 0

    if args.json:
        print(json.dumps(rows, indent=2, sort_keys=True))
    elif args.issue_body:
        for agent, agent_rows in agents_needing_issues(rows).items():
            print(issue_body_for_agent(agent, agent_rows))
            print()
    else:
        print("%-24s %-11s %-12s %-12s %-9s %s" % ("agent", "verdict", "recorded", "current", "age", "note"))
        for r in rows:
            print(
                "%-24s %-11s %-12s %-12s %-9s %s"
                % (
                    _label(r),
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
            print("  no drift can ever be computed for: %s" % ", ".join(_label(r) for r in unusable))

    return 1 if (args.fail_on_drift and drifted(rows)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
