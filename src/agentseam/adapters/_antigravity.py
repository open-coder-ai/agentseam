"""The F5 `antigravity` family: event-less payloads classified by shape.

Only the shape inference is code (dialect-families.md §3.3) -- the verdicts are the
engine's G1 renderer over `data/vendors/antigravity.json`'s word tables.
"""

from __future__ import annotations

from ._hook_json import hj_respond
from ._payload import hj_parse


def antigravity_wire(raw):
    """Name the event from shape; ties go to PreToolUse so the gate stays a gate."""
    if "terminationReason" in raw or "fullyIdle" in raw:
        return "Stop"
    if isinstance(raw.get("toolCall"), dict):
        return "PostToolUse" if "error" in raw else "PreToolUse"
    return None


def antigravity_claims(cfg, raw):
    """Structural: `conversationId` with `workspacePaths` is Antigravity's own envelope."""
    if not isinstance(raw, dict):
        return False
    return "conversationId" in raw and isinstance(raw.get("workspacePaths"), list)


def antigravity_parse(cfg, raw):
    return hj_parse(cfg, raw, wire=antigravity_wire(raw))


def antigravity_respond(cfg, decision, event):
    return hj_respond(cfg, decision, event, wire=antigravity_wire(event.raw or {}))
