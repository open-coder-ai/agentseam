"""The generated vendor examples must stay true, and must cover every hook we claim."""

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
from vendor_payloads import SECRET  # noqa: E402

import agentseam as A  # noqa: E402

PAIRS = sorted((agent, event) for agent, events in SCENARIOS.items() for event in events)


@pytest.fixture(scope="module")
def generated():
    return build()


def test_committed_pages_match_what_the_library_produces(generated):
    """An example nobody regenerates is a claim nobody checks."""
    stale = [
        name
        for name, body in sorted(generated.items())
        if (open(os.path.join(OUT, name)).read() if os.path.exists(os.path.join(OUT, name)) else None) != body
    ]
    assert not stale, "stale examples, run `python3 examples/generate.py`: %s" % ", ".join(stale)


def test_no_committed_page_is_orphaned(generated):
    assert {p for p in os.listdir(OUT) if p.endswith(".md")} == set(generated)


@pytest.mark.parametrize("agent", sorted(SCENARIOS))
def test_every_hook_the_matrix_claims_has_an_example(agent):
    """Both directions. A claimed hook with no example hides a capability; an example for an"""
    assert set(SCENARIOS[agent]) == set(A.MATRIX[agent]["events"])


@pytest.mark.parametrize("agent,event", PAIRS)
def test_each_payload_parses_to_the_event_it_is_filed_under(agent, event):
    """A payload filed under the wrong event would document the wrong hook's behaviour."""
    assert A.adapters.get(agent).parse(SCENARIOS[agent][event]).event == event


@pytest.mark.parametrize("agent,event", PAIRS)
def test_each_payload_is_claimed_by_its_own_adapter(agent, event):
    """Necessary for the page to be about the agent it names."""
    assert A.adapters.get(agent).claims(SCENARIOS[agent][event])


@pytest.mark.parametrize("agent,event", PAIRS)
def test_a_payload_is_never_claimed_by_exactly_one_wrong_adapter(agent, event):
    """Ambiguity is allowed and documented; being confidently wrong is not."""
    raw = SCENARIOS[agent][event]
    claimants = [n for n, m in A.adapters.ADAPTERS.items() if m.claims(raw)]
    detected = A.adapters.detect(raw)
    assert detected in (agent, None), "detected %s for a %s payload" % (detected, agent)
    if detected is None:
        assert len(claimants) > 1, "nobody claims this payload, so it would be allowed through"


@pytest.mark.parametrize("agent,event", PAIRS)
def test_every_page_shows_the_hook_and_its_vendor_name(generated, agent, event):
    page = generated["%s.md" % agent]
    assert "`%s`" % event in page
    assert "`%s`" % A.adapters.get(agent).REVERSE_EVENT_MAP[event] in page


def test_every_adapted_agent_has_a_page():
    assert set(SCENARIOS) == set(A.adapted_agents())


@pytest.mark.parametrize("agent", sorted(SCENARIOS))
def test_the_pre_tool_example_really_is_the_shared_story(agent):
    """Pages only compare if the situation is held constant."""
    event = A.adapters.get(agent).parse(SCENARIOS[agent][A.PRE_TOOL])
    assert SECRET in (event.content or "") or SECRET in (event.command or ""), agent


@pytest.mark.parametrize("agent", sorted(SCENARIOS))
def test_every_page_states_what_its_claims_rest_on(generated, agent):
    """Most of these rows are read from vendor docs. A reader must not have to guess which."""
    from agentseam.matrix import basis

    page = generated["%s.md" % agent]
    assert "How this was established" in page
    assert basis(agent) in page
    assert "Confirm against your own" in page


def test_the_index_says_the_pages_are_not_observations(generated):
    index = generated["README.md"]
    assert "not what their builds were observed" in index
    assert "Verify against your own installation" in index


KNOWN_AMBIGUOUS = {
    ("gemini_cli", "session_start"),
    ("gemini_cli", "session_end"),
    ("tabnine", "session_start"),
    ("vscode_copilot", "session_start"),
}


def test_every_shipping_payload_resolves_to_its_own_adapter():
    """The corpus that generates the published docs, not just the hand-kept fixture list."""
    from scenarios import SCENARIOS

    from agentseam import adapters

    wrong = []
    for agent, events in sorted(SCENARIOS.items()):
        for event, raw in sorted(events.items()):
            claimants = [name for name, mod in sorted(adapters.ADAPTERS.items()) if mod.claims(raw)]
            if claimants != [agent] and (agent, event) not in KNOWN_AMBIGUOUS:
                wrong.append("%s/%s claimed by %s" % (agent, event, claimants or "nobody"))
    assert not wrong, "shipping payloads not claimed by exactly their own adapter:\n  " + "\n  ".join(wrong)


def test_the_known_ambiguous_set_is_still_ambiguous():
    """A pinned exception must expire when it stops being true."""
    from scenarios import SCENARIOS

    from agentseam import adapters

    for agent, event in sorted(KNOWN_AMBIGUOUS):
        raw = SCENARIOS[agent][event]
        claimants = [name for name, mod in sorted(adapters.ADAPTERS.items()) if mod.claims(raw)]
        assert claimants != [agent], "%s/%s now resolves cleanly -- drop it from KNOWN_AMBIGUOUS" % (agent, event)
