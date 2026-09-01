"""Replay the golden wire fixtures (docs/design/dialect-families.md §5-6, wave D1).

Every fixture freezes what today's adapters actually say -- (payload -> stdout, exit) for
every scenario event x the six Decision outcomes, plus `hook_config()` on both matcher
paths. Re-derive with `tools/capture_fixtures.py`; this test proves the frozen bytes are
still what the adapters produce, so every later dialect-engine wave gates on an empty diff.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from capture_fixtures import OUTCOMES  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import adapters  # noqa: E402

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "golden"
_OUTCOME_FACTORY = dict(OUTCOMES)


def _load(agent):
    return json.loads((FIXTURE_DIR / ("%s.json" % agent)).read_text(encoding="utf-8"))


FIXTURES = {agent: _load(agent) for agent in sorted(adapters.ADAPTERS)}


def test_a_fixture_exists_for_every_adapter():
    """A missing fixture file is a silent coverage gap, not a pass."""
    assert set(FIXTURES) == set(adapters.ADAPTERS)


def test_every_fixture_covers_every_outcome_the_scenario_offers():
    """A fixture set that misses an outcome is the gap the next wave falls through."""
    outcome_names = {name for name, _ in OUTCOMES}
    gaps = [
        "%s/%s missing %s" % (agent, event, sorted(outcome_names - set(entry["outcomes"])))
        for agent, data in FIXTURES.items()
        for event, entry in data["events"].items()
        if outcome_names - set(entry["outcomes"])
    ]
    assert not gaps, "\n".join(gaps)


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_wire_output_matches_the_frozen_fixture(agent):
    """Replay every frozen payload through today's adapter; the diff must be empty."""
    mismatches = []
    for event, entry in sorted(FIXTURES[agent]["events"].items()):
        payload = entry["payload"]
        for outcome, expected in sorted(entry["outcomes"].items()):
            factory = _OUTCOME_FACTORY[outcome]
            text, code, _event, _decision = A.handle(payload, lambda _e, f=factory: f(), agent=agent)
            actual = {"stdout": text, "exit": code}
            if actual != expected:
                mismatches.append("%s/%s: expected %r, got %r" % (event, outcome, expected, actual))
    assert not mismatches, "\n".join(mismatches)


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_hook_config_matches_the_frozen_fixture_on_both_matcher_paths(agent):
    """`hook_config()` replayed with no matcher, and with one -- both wire shapes frozen."""
    mod = adapters.get(agent)
    frozen = FIXTURES[agent]["hook_config"]
    events, command = frozen["events"], frozen["command"]
    assert mod.hook_config(events, command) == frozen["no_matcher"]
    matcher = frozen["with_matcher"]["matcher"]
    assert mod.hook_config(events, command, matcher=matcher) == frozen["with_matcher"]["config"]
