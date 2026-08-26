"""Agents we do not hook, and why -- kept apart from the rows we actively maintain.

Two different states live here, and collapsing them would be a lie in one direction or the
other:

  * `TIER_NONE` is a claim about the **agent**: it exposes no hook surface at all.
  * `TIER_UNADAPTED` is a claim about **us**: the agent may well expose one, we just have
    no adapter for it. Instruction files still reach these agents; only tool-call gating
    is missing.

The second kind is a placeholder, and placeholders go stale in a way verified claims do
not -- Cursor and Devin both sat here until their vendor documentation turned up, and one
of these rows asserted Devin had "no pre-tool-use surface" when it has had one all along.
Keeping them in a separate file is a reminder that they are inherited, not established.
"""

from __future__ import annotations

from .matrix_data import TIER_NONE, TIER_UNADAPTED

GAPS = {
    "kimi_code": {
        "display": "Kimi Code",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": {
            "version": "n/a",
            "date": "2026-08-26",
            "method": "sibling project's shipped surface matrix (no pre-tool-use surface); not re-verified here",
        },
        "events": {},
        "notes": "No hook adapter in agentseam. Instruction files are supported "
        "(see agentseam.instructions); tool calls cannot be gated here yet.",
    },
    "replit": {
        "display": "Replit",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": {
            "version": "n/a",
            "date": "2026-08-26",
            "method": "sibling project's shipped surface matrix (no pre-tool-use surface); not re-verified here",
        },
        "events": {},
        "notes": "No hook adapter in agentseam. Instruction files are supported "
        "(see agentseam.instructions); tool calls cannot be gated here yet.",
    },
    "tabnine": {
        "display": "Tabnine",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": {
            "version": "n/a",
            "date": "2026-08-26",
            "method": "sibling project's shipped surface matrix (no pre-tool-use surface); not re-verified here",
        },
        "events": {},
        "notes": "No hook adapter in agentseam. Instruction files are supported "
        "(see agentseam.instructions); tool calls cannot be gated here yet.",
    },
    "junie": {
        "display": "JetBrains Junie",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": {
            "version": "n/a",
            "date": "2026-08-26",
            "method": "not yet researched from a primary source here; a Junie CLI hook surface is reported but unverified",
        },
        "events": {},
        "notes": "No hook adapter in agentseam. Instruction files are supported "
        "(see agentseam.instructions); tool calls cannot be gated here yet.",
    },
    "zed": {
        "display": "Zed",
        "tier": TIER_NONE,
        "config": None,
        "verified": {"version": "2026-08", "date": "2026-08-26", "method": "docs + open extensibility issues"},
        "events": {},
        "notes": "No user hooks. Only declarative agent.tool_permissions rules. "
        "No deny path for an external handler — say so rather than stretch.",
    },
    "aider": {
        "display": "Aider",
        "tier": TIER_NONE,
        "config": None,
        "verified": {"version": "2026-08", "date": "2026-08-26", "method": "docs/config reference"},
        "events": {},
        "notes": "No lifecycle hooks. Only --lint-cmd/--test-cmd post-edit steps. "
        "Observation possible via git hooks; no interception.",
    },
}
