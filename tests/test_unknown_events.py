"""A vendor event we do not map must be reported as unknown, never guessed at.

Vendors add hook events without warning -- Claude Code's own list is around thirty and has
grown. Before this, four adapters answered an unmapped event by falling back to the nearest
canonical one, so a `TeammateIdle` payload arrived at a handler labelled `pre_tool` and
invited it to evaluate a pre-tool policy against something that was not one. Two others
returned a non-canonical value, and two raised, taking the hook down.

The capture tooling found this by feeding an adapter an event nobody had mapped, which is
exactly what a live run does.
"""

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

#: Carries every naming convention at once, so each adapter sees a name it cannot know.
NOVEL = {
    "hook_event_name": "TeammateIdle",
    "hookEventName": "teammateIdle",
    "client_type": "kimi_code_cli",
    "tool_name": "x",
    "tool_input": {},
    "session_id": "s",
}

#: Antigravity's payloads never carry an event name, so shape is all it has. Its unknown
#: case is a payload matching none of the shapes it knows.
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
    """Two adapters used to raise KeyError, which takes the hook process down.

    Most agents fail open on a crashed hook, so that turned an unknown event into a silently
    permitted one -- with a stack trace as the only trace.
    """
    A.adapters.get(agent).parse(_novel_for(agent))


@pytest.mark.parametrize("agent", sorted(A.adapters.ADAPTERS))
def test_the_handler_is_not_asked_about_an_event_it_cannot_reason_about(agent):
    """Handlers reason about the canonical vocabulary. Handing them something outside it
    invites a decision made on a false premise, so the dispatcher answers for them.
    """
    called = []

    def handler(event):
        called.append(event.event)
        return Decision.deny("must not be reached")

    text, code, event, decision = A.handle(_novel_for(agent), handler, agent=agent)
    assert called == [], "handler was asked about %s" % called
    assert decision.outcome == A.ALLOW
    assert (text, code) == ("", 0)
    # The event still comes back, so a caller that wants to log the surprise can.
    assert event.event == UNKNOWN
    assert event.raw


@pytest.mark.parametrize("agent", sorted(A.adapters.ADAPTERS))
def test_a_known_event_still_reaches_the_handler(agent):
    """The guard must not have swallowed the normal path."""
    from scenarios import SCENARIOS

    called = []
    A.handle(SCENARIOS[agent][A.PRE_TOOL], lambda e: called.append(e.event) or Decision.allow(), agent=agent)
    assert called == [A.PRE_TOOL]
