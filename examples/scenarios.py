"""The scenarios the generated example pages are built from: one per agent, per event.

`SCENARIOS[agent][event]` is a payload in that agent's own dialect. The set of events comes
from the matrix, so the pages cover exactly what each agent is claimed to support -- no
more, which would document coverage that does not exist, and no less, which would leave a
claimed hook with nothing showing what it looks like.

The story is held constant per event so the pages compare. Every `pre_tool` is the same
attempt to write a credential into a file the agent will read back later; every
`tool_failure` is the same failed test command. What differs between pages is the vendor's
shape, which is the whole point of having pages per vendor.

Payloads are written from the vendor documentation behind each adapter rather than copied
from the test fixtures -- an example that only proves the tests agree with themselves proves
nothing. What the tests do check is stronger: every payload must be claimed by exactly the
agent it is filed under, and must parse to the event it is filed under.
"""

from __future__ import annotations

from vendor_payloads import SECRET, payload

from agentseam import adapters
from agentseam.contract import EVENTS
from agentseam.matrix_data import MATRIX


def _build():
    out = {}
    for agent in sorted(adapters.ADAPTERS):
        reverse = adapters.get(agent).REVERSE_EVENT_MAP
        # EVENTS rather than the matrix dict, so pages order events by the lifecycle
        # instead of by however the row happened to be written.
        rows = [e for e in EVENTS if e in MATRIX[agent]["events"]]
        out[agent] = {event: payload(agent, event, reverse[event]) for event in rows}
    return out


#: agent -> canonical event -> payload.
SCENARIOS = _build()

__all__ = ["SCENARIOS", "SECRET"]
