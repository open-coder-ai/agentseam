"""Queries over the per-agent capability matrix."""

from __future__ import annotations

from .matrix_data import MATRIX
from .matrix_terms import (
    BASES,
    BASIS_INHERITED,
    BASIS_LIVE,
    BASIS_LIVE_PARTIAL,
    FAIL_CLOSED,
    FAIL_CONFIGURABLE,
    FAIL_OPEN,
    TIER_BLOCK,
    TIER_FULL,
    TIER_NONE,
    TIER_OBSERVE,
    TIER_UNADAPTED,
    _cap,
)

__all__ = [
    "BASES",
    "BASIS_INHERITED",
    "BASIS_LIVE",
    "BASIS_LIVE_PARTIAL",
    "FAIL_CLOSED",
    "FAIL_CONFIGURABLE",
    "FAIL_OPEN",
    "MATRIX",
    "TIER_BLOCK",
    "TIER_FULL",
    "TIER_NONE",
    "TIER_OBSERVE",
    "TIER_UNADAPTED",
    "adapted_agents",
    "agents",
    "basis",
    "can_block",
    "can_rewrite",
    "can_transform",
    "capability",
    "enforcement_level",
    "observed",
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


def can_transform(agent, event):
    """ACS-named alias of can_rewrite() -- same capability, same value."""
    return bool(capability(agent, event)["transform"])


def enforcement_level(agent, event):
    """The honest word for what a consumer may claim at this surface."""
    cap = capability(agent, event)
    if cap["block"]:
        if cap["fail_mode"] == FAIL_CLOSED:
            return "enforced"
        return "enforceable" if cap["fail_mode"] == FAIL_CONFIGURABLE else "best-effort"
    row = MATRIX.get(agent)
    if row and event in row["events"]:
        return "detect"
    return "none"


def basis(agent):
    """What KIND of evidence this agent's row rests on, from the closed `BASES` vocabulary."""
    row = MATRIX.get(agent)
    return row["verified"].get("basis") if row else None


def observed(agent):
    """Canonical events actually seen fire against the running agent."""
    row = MATRIX.get(agent)
    return tuple(row["verified"].get("observed", ())) if row else ()


def agents():
    return sorted(MATRIX)


def adapted_agents():
    """Agents agentseam can actually hook. Everything else is instruction-files only."""
    return sorted(a for a, row in MATRIX.items() if row["tier"] not in (TIER_NONE, TIER_UNADAPTED))
