"""Recount `data/vendors/<agent>.json` from the current adapters -- see `recount(agent)`.

Split by activity (tests/test_repo_standards.py's 300-line budget): `mechanical.py` (module
constants), `fields.py` (AST-read field-fallback chains), `gates.py` (golden-fixture-replayed
verdict grammar), `hook_entry.py` (golden-fixture-replayed hook_config() shape), `tables.py`
(the design's own stated judgment calls: family assignment, marker claims, evidence).
"""

from __future__ import annotations

from agentseam import adapters

from .fields import fields as _fields
from .gates import verdicts as _verdicts
from .hook_entry import hook_entry as _hook_entry
from .mechanical import mechanical as _mechanical
from .mechanical import wire_events as _wire_events
from .tables import claims as _claims
from .tables import evidence as _evidence
from .tables import family as _family

__all__ = ["recount", "build_all"]


def recount(agent):
    """The full `data/vendors/<agent>.json` entry, recounted from the current adapter."""
    mod = adapters.get(agent)
    entry = _mechanical(agent, mod)
    entry["family"] = _family(agent)
    wire_events = _wire_events(mod)
    if wire_events:
        entry["wire_events"] = wire_events
    entry["claims"] = _claims(agent)
    entry.update(_fields(agent, mod))
    entry["verdicts"] = _verdicts(agent, mod)
    entry["hook_entry"] = _hook_entry(agent)
    entry["evidence"] = _evidence(agent)
    return entry


def build_all():
    return {agent: recount(agent) for agent in sorted(adapters.ADAPTERS)}
