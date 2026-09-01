"""Bundle equivalence (dialect-families.md §5.5): generated runtime == library, per vendor,

over the whole golden set -- every frozen payload x outcome, plus hook_config's two paths."""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from capture_fixtures import OUTCOMES  # noqa: E402

from agentseam import adapters, bundler  # noqa: E402

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "golden"


def _fixture(agent):
    return json.loads((FIXTURE_DIR / ("%s.json" % agent)).read_text(encoding="utf-8"))


def _bundle_namespace(agent):
    namespace = {"__name__": "_bundle_%s" % agent}
    exec(compile(bundler.bundle(agent), "<bundle:%s>" % agent, "exec"), namespace)  # noqa: S102 - the artifact under test
    return namespace


def _bundle_factories(namespace):
    """The six frozen outcomes rebuilt on the bundle's own Decision class."""
    decision = namespace["Decision"]
    factories = {
        "allow": lambda: decision.allow(),
        "deny": lambda: decision.deny("policy"),
        "ask": lambda: decision.ask("confirm"),
        "rewrite": lambda: decision.rewrite({"content": "safe"}, "redacted"),
        "rewrite-without-input": lambda: decision.rewrite(None, "needs change"),
        "vouch": lambda: decision.vouch("trusted"),
    }
    assert set(factories) == {name for name, _ in OUTCOMES}, "outcome tables drifted; update both"
    return factories


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_the_bundle_replays_the_golden_wire_fixtures(agent):
    """Run every frozen payload x outcome through the bundle's own main(); empty diff."""
    namespace = _bundle_namespace(agent)
    factories = _bundle_factories(namespace)
    mismatches = []
    for event, entry in sorted(_fixture(agent)["events"].items()):
        payload = json.dumps(entry["payload"])
        for outcome, expected in sorted(entry["outcomes"].items()):
            namespace["handle"] = lambda _e, factory=factories[outcome]: factory()
            out = io.StringIO()
            code = namespace["main"](stdin=io.StringIO(payload), stdout=out, exit=False)
            actual = {"stdout": out.getvalue(), "exit": code}
            if actual != expected:
                mismatches.append("%s/%s: expected %r, got %r" % (event, outcome, expected, actual))
    assert not mismatches, "\n".join(mismatches)


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_the_bundles_hook_config_matches_the_frozen_fixture(agent):
    frozen = _fixture(agent)["hook_config"]
    namespace = _bundle_namespace(agent)
    events, command = frozen["events"], frozen["command"]
    assert namespace["hook_config"](events, command) == frozen["no_matcher"]
    matcher = frozen["with_matcher"]["matcher"]
    assert namespace["hook_config"](events, command, matcher=matcher) == frozen["with_matcher"]["config"]
