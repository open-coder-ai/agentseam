"""Primitive 3 limits: the per-vendor packaging gaps, read from data/packaging-limits.json."""

from __future__ import annotations

from ._data import load

_TABLE = load("packaging-limits.json")

PART_LIMITS = {
    (agent, part): reason for agent, parts in _TABLE["part_limits"].items() for part, reason in parts.items()
}

ALSO_READS = _TABLE["also_reads"]

UNRECORDED = _TABLE["unrecorded"]
