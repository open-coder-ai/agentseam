"""Agents we do not hook, and why -- kept apart from the rows we actively maintain."""

from __future__ import annotations

from .matrix_evidence import EVIDENCE
from .matrix_notes import NOTES
from .matrix_terms import TIER_NONE, TIER_UNADAPTED

GAPS = {
    "copilot": {
        "display": "GitHub Copilot (Agent Plugins 1.0 marketplace bundle)",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": EVIDENCE["copilot"],
        "events": {},
        "notes": NOTES["copilot"],
    },
    "replit": {
        "display": "Replit Agent",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": EVIDENCE["replit"],
        "events": {},
        "notes": NOTES["replit"],
    },
    "zed": {
        "display": "Zed",
        "tier": TIER_NONE,
        "config": None,
        "verified": EVIDENCE["zed"],
        "events": {},
        "notes": "No user hooks. Only declarative agent.tool_permissions rules. "
        "No deny path for an external handler — say so rather than stretch.",
    },
    "aider": {
        "display": "Aider",
        "tier": TIER_NONE,
        "config": None,
        "verified": EVIDENCE["aider"],
        "events": {},
        "notes": "No lifecycle hooks. Only --lint-cmd/--test-cmd post-edit steps. "
        "Observation possible via git hooks; no interception.",
    },
}
