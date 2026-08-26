"""The vocabulary the matrix asserts in: fail modes, coverage tiers, and the cell shape.

Kept apart from the rows because defining what a word is allowed to mean is a different
activity from claiming it about an agent -- and the words are where this project's honesty
actually lives. Every one of them exists to stop a claim from being rounded up: `open` vs
`configurable`, `unadapted` vs `none`.
"""

from __future__ import annotations

# fail_mode: what the AGENT does when the hook crashes/times out.
#   "closed" -> the action is blocked (safe)
#   "open"   -> the action proceeds (a policy claiming enforcement here is overclaiming)
FAIL_CLOSED = "closed"
FAIL_OPEN = "open"
#: The agent fails open by default but can be told to fail closed per hook (Cursor's
#: `failClosed: true`). Neither existing value tells the truth about that: "open" would
#: understate a surface a user can make airtight, and "closed" would claim a default that
#: is not there. What a consumer may claim depends on how the hook was installed.
FAIL_CONFIGURABLE = "configurable"

# tier: how much of the surface the adapter can serve.
TIER_FULL = "block+rewrite"
TIER_BLOCK = "block"
TIER_OBSERVE = "observe"
TIER_NONE = "none"
#: Known agent, no hook adapter in agentseam. Distinct from TIER_NONE, which is a claim
#: about the AGENT (it exposes nothing to hook). This one is a claim about US, and it
#: matters: a user can still push instruction files to these agents, they just cannot
#: gate tool calls here yet. Collapsing the two would either slander the agent or
#: overstate our coverage.
TIER_UNADAPTED = "unadapted"


def _cap(block=False, rewrite=False, fail=FAIL_OPEN):
    return {"block": block, "rewrite": rewrite, "fail_mode": fail}
