#!/usr/bin/env python3
"""Capture golden wire fixtures: today's adapters' real (payload -> stdout, exit) output.

    python3 tools/capture_fixtures.py
    python3 tools/capture_fixtures.py --check   # exit 1 if any fixture differs from source

Writes `tests/fixtures/golden/<agent>.json`, one file per agent, driven by running the
actual adapters through `agentseam.handle()` -- never transcribed by hand. This is the
frozen baseline every later dialect-engine wave (docs/design/dialect-families.md §6,
D3-D6) must reproduce byte-for-byte; re-running this script replaces that baseline, so
only do it deliberately, after confirming any output change is intended.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "examples"))

from scenarios import SCENARIOS  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import adapters  # noqa: E402

FIXTURE_DIR = os.path.join(ROOT, "tests", "fixtures", "golden")

#: outcome name -> Decision factory. The six shapes a handler may ever return, exactly
#: tests/test_decision_vocabulary.py:34-41 -- keep the two in sync by hand, they are small.
OUTCOMES = (
    ("allow", lambda: A.Decision.allow()),
    ("deny", lambda: A.Decision.deny("policy")),
    ("ask", lambda: A.Decision.ask("confirm")),
    ("rewrite", lambda: A.Decision.rewrite({"content": "safe"}, "redacted")),
    ("rewrite-without-input", lambda: A.Decision.rewrite(None, "needs change")),
    ("vouch", lambda: A.Decision.vouch("trusted")),
)

#: hook_config is captured on both matcher paths with these fixed arguments.
HOOK_CONFIG_COMMAND = "python3 guard.py"
HOOK_CONFIG_MATCHER = "Bash"


def _speak(agent, payload, factory):
    """One (stdout, exit) pair, driven through the real dispatcher -- degrade() included."""
    text, code, _event, _decision = A.handle(payload, lambda _e: factory(), agent=agent)
    return {"stdout": text, "exit": code}


def _capture_events(agent):
    events = {}
    for event, payload in sorted(SCENARIOS[agent].items()):
        events[event] = {
            "payload": payload,
            "outcomes": {name: _speak(agent, payload, factory) for name, factory in OUTCOMES},
        }
    return events


def _capture_hook_config(mod, canonical_events):
    no_matcher = mod.hook_config(canonical_events, HOOK_CONFIG_COMMAND)
    with_matcher = mod.hook_config(canonical_events, HOOK_CONFIG_COMMAND, matcher=HOOK_CONFIG_MATCHER)
    return {
        "command": HOOK_CONFIG_COMMAND,
        "events": canonical_events,
        "no_matcher": no_matcher,
        "with_matcher": {"matcher": HOOK_CONFIG_MATCHER, "config": with_matcher},
    }


def capture(agent):
    """The full fixture for one agent: every scenario event x every outcome, plus hook_config."""
    mod = adapters.get(agent)
    events = _capture_events(agent)
    return {
        "agent": agent,
        "events": events,
        "hook_config": _capture_hook_config(mod, sorted(events)),
    }


def render(agent):
    """The exact bytes of one agent's fixture file."""
    return json.dumps(capture(agent), indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def fixture_path(agent, fixture_dir=FIXTURE_DIR):
    return os.path.join(fixture_dir, "%s.json" % agent)


def drifted(fixture_dir=FIXTURE_DIR):
    """Agents whose committed fixture is not what a capture from today's source writes."""
    stale = []
    for agent in sorted(adapters.ADAPTERS):
        try:
            with open(fixture_path(agent, fixture_dir), encoding="utf-8", newline="") as fh:
                current = fh.read()
        except FileNotFoundError:
            current = None
        if current != render(agent):
            stale.append(agent)
    return stale


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args not in ([], ["--check"]):
        print("usage: capture_fixtures.py [--check]", file=sys.stderr)
        return 2
    if args == ["--check"]:
        stale = drifted()
        for agent in stale:
            print("drift: %s" % fixture_path(agent))
        return 1 if stale else 0
    os.makedirs(FIXTURE_DIR, exist_ok=True)
    for agent in sorted(adapters.ADAPTERS):
        path = fixture_path(agent)
        with open(path, "w", encoding="utf-8", newline="") as fh:
            fh.write(render(agent))
        print("wrote %s (%d events x %d outcomes)" % (path, len(SCENARIOS[agent]), len(OUTCOMES)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
