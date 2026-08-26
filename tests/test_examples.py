"""The generated vendor examples must stay true.

Documentation that describes behaviour the code no longer has is worse than none: it is a
confident wrong answer. So the example pages are generated from the real code paths, and
this file fails when the committed pages drift from what the library now produces.

The second thing checked here matters as much: every scenario payload must be claimed by
exactly the agent whose page it appears on. Without that, a page could quietly document one
vendor's dialect under another vendor's name.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

import pytest  # noqa: E402
from generate import OUT, build  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402

import agentseam as A  # noqa: E402


@pytest.fixture(scope="module")
def generated():
    return build()


def test_committed_pages_match_what_the_library_produces(generated):
    """The whole point: an example nobody regenerates is a claim nobody checks."""
    stale = []
    for name, body in sorted(generated.items()):
        path = os.path.join(OUT, name)
        current = open(path).read() if os.path.exists(path) else None
        if current != body:
            stale.append(name)
    assert not stale, "stale examples, run `python3 examples/generate.py`: %s" % ", ".join(stale)


def test_no_committed_page_is_orphaned(generated):
    """A page for an agent the generator no longer emits would linger and mislead."""
    on_disk = {p for p in os.listdir(OUT) if p.endswith(".md")}
    assert on_disk == set(generated)


@pytest.mark.parametrize("agent", sorted(SCENARIOS))
def test_each_scenario_is_claimed_by_exactly_the_agent_it_documents(agent):
    """A payload claimed by two adapters, or by the wrong one, would document the wrong agent.

    This is the same discipline the dispatcher tests apply to fixtures, pointed at the
    examples -- and it caught a real one: a Cursor payload without `model` was claimed by
    VS Code Copilot too, because that adapter's only defence was a field belonging to
    another vendor's schema.
    """
    claimants = [n for n, m in A.adapters.ADAPTERS.items() if m.claims(SCENARIOS[agent])]
    assert claimants == [agent]


def test_every_adapted_agent_has_a_page():
    """A missing page reads as an agent we cannot handle, which would understate coverage."""
    assert set(SCENARIOS) == set(A.adapted_agents())


@pytest.mark.parametrize("agent", sorted(SCENARIOS))
def test_each_scenario_really_is_the_same_situation(agent):
    """Pages are only comparable if the scenario is held constant across vendors.

    Windsurf is the documented exception, and the reason is the finding: it has no
    file-write event at all, so the nearest thing it can see is the shell command that
    would do the writing.
    """
    event = A.adapters.get(agent).parse(SCENARIOS[agent])
    assert event.event == A.PRE_TOOL
    seen = "%s %s" % (event.path or "", event.command or "")
    assert "AWS_SECRET" in (event.content or "") or "AWS_SECRET" in seen, agent


def test_a_page_never_promises_enforcement_the_matrix_does_not_claim(generated):
    """The pages quote the matrix rather than restating it, so this guards the wiring."""
    for agent in SCENARIOS:
        page = generated["%s.md" % agent]
        assert "**%s**" % A.enforcement_level(agent, A.PRE_TOOL) in page, agent
