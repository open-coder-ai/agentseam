"""Queries over the per-agent capability matrix.

The data itself is in `matrix_data.py`; this module answers the question a consumer
actually has: what may I honestly claim about this agent at this event?
"""

from __future__ import annotations

from .matrix_data import (
    FAIL_CLOSED,
    FAIL_OPEN,
    MATRIX,
    TIER_BLOCK,
    TIER_FULL,
    TIER_NONE,
    TIER_OBSERVE,
    TIER_UNADAPTED,
    _cap,
)

__all__ = [
    "MATRIX",
    "capability",
    "can_block",
    "can_rewrite",
    "enforcement_level",
    "agents",
    "adapted_agents",
    "FAIL_CLOSED",
    "FAIL_OPEN",
    "TIER_FULL",
    "TIER_BLOCK",
    "TIER_OBSERVE",
    "TIER_NONE",
    "TIER_UNADAPTED",
]


def capability(agent, event):
    """What `agent` can do at `event`. Unknown agent/event -> no capability."""
    row = MATRIX.get(agent)
    if not row:
        return _cap()
    return row["events"].get(event, _cap())


def can_block(agent, event):
    return bool(capability(agent, event)["block"])


def can_rewrite(agent, event):
    return bool(capability(agent, event)["rewrite"])


def enforcement_level(agent, event):
    """The honest word for what a consumer may claim at this surface.

    enforced  - the agent blocks, and fails closed if our hook dies
    best-effort - the agent blocks, but fails open (a crash silently allows)
    detect    - we see it after the fact; prevention is not available
    none      - no surface at all
    """
    cap = capability(agent, event)
    if cap["block"]:
        return "enforced" if cap["fail_mode"] == FAIL_CLOSED else "best-effort"
    row = MATRIX.get(agent)
    if row and event in row["events"]:
        return "detect"
    return "none"


def agents():
    return sorted(MATRIX)


def adapted_agents():
    """Agents agentseam can actually hook. Everything else is instruction-files only."""
    return sorted(a for a, row in MATRIX.items() if row["tier"] not in (TIER_NONE, TIER_UNADAPTED))
