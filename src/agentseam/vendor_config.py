"""The vendor config entries (docs/design/dialect-families.md D2) and their schema.

Unused by the runtime today -- D3+ wires an engine onto this data. Loaded with the PR #89
loader pattern (`_data.py`), same as the capability matrix: every JSON array comes back as
a tuple. [h] (dialect-families.md §7) asked whether that collides with `fields`' order-
sensitive lists; it does not, because a tuple preserves the exact sequence its JSON array
was written in, and nothing here (or in `_data.py` itself) ever compares one of these
tuples against a list literal with `==`.
"""

from __future__ import annotations

from ._data import load
from .adapters import ADAPTERS

SCHEMA = load("vendors/schema.json")

VENDOR_CONFIG = {agent: load("vendors/%s.json" % agent) for agent in sorted(ADAPTERS)}

__all__ = ["SCHEMA", "VENDOR_CONFIG"]
