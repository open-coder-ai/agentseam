"""A vendor event we do not map must be reported as unknown, never guessed at."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

import pytest  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402
from agentseam.contract import EVENTS, UNKNOWN  # noqa: E402

NOVEL = {
    "hook_event_name": "TeammateIdle",
    "hookEventName": "teammateIdle",
    "client_type": "kimi_code_cli",
    "tool_name": "x",
    "tool_input": {},
    "session_id": "s",
}

ANTIGRAVITY_NOVEL = {"conversationId": "x", "workspacePaths": ["/r"], "invocationNum": 3, "initialNumSteps": 10}


def _novel_for(agent):
    return ANTIGRAVITY_NOVEL if agent == "antigravity" else NOVEL


def test_unknown_is_outside_the_canonical_vocabulary():
    """So a handler matching on the vocabulary can never match it by accident."""
    assert UNKNOWN not in EVENTS


@pytest.mark.parametrize("agent", sorted(A.adapters.ADAPTERS))
def test_an_unmapped_event_is_never_relabelled_as_a_real_one(agent):
    event = A.adapters.get(agent).parse(_novel_for(agent))
    assert event.event == UNKNOWN, "reported an unmapped event as %r" % event.event


@pytest.mark.parametrize("agent", sorted(A.adapters.ADAPTERS))
def test_parsing_an_unmapped_event_does_not_raise(agent):
    """Two adapters used to raise KeyError, which takes the hook process down."""
    A.adapters.get(agent).parse(_novel_for(agent))


@pytest.mark.parametrize("agent", sorted(A.adapters.ADAPTERS))
def test_the_handler_is_not_asked_about_an_event_it_cannot_reason_about(agent):
    """Handlers reason about the canonical vocabulary. Handing them something outside it"""
    called = []

    def handler(event):
        called.append(event.event)
        return Decision.deny("must not be reached")

    text, code, event, decision = A.handle(_novel_for(agent), handler, agent=agent)
    assert called == [], "handler was asked about %s" % called
    assert decision.outcome == A.ALLOW
    assert (text, code) == ("", 0)
    assert event.event == UNKNOWN
    assert event.raw


@pytest.mark.parametrize("agent", sorted(A.adapters.ADAPTERS))
def test_a_known_event_still_reaches_the_handler(agent):
    """The guard must not have swallowed the normal path."""
    from scenarios import SCENARIOS

    called = []
    A.handle(SCENARIOS[agent][A.PRE_TOOL], lambda e: called.append(e.event) or Decision.allow(), agent=agent)
    assert called == [A.PRE_TOOL]
