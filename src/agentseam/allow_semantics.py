"""What a bare ALLOW means to each vendor, audited per agent in data/allow-semantics.json.

The rule the table encodes: a bare ALLOW must land on whatever the vendor would have done
with no hook at all. Usually that is silence, but not always (on Cursor an empty response
is a hook error), and where silence is unavailable the adapter must speak -- each row's
note records the evidence. UNVERIFIED is a real answer, deliberately not resolved by
picking the safer-sounding option: both directions are guesses, and this project records
the gap instead of guessing vendor shapes.
"""

from __future__ import annotations

from ._data import load

ALLOW_SILENT = "silent"

ALLOW_INERT = "inert"

ALLOW_REQUIRED = "required"

ALLOW_UNVERIFIED = "unverified"

_TABLE = load("allow-semantics.json")

ALLOW_SEMANTICS = {agent: (row["bare_allow"], row["note"]) for agent, row in _TABLE["semantics"].items()}

VOUCH_SPEAKS = frozenset(agent for agent, row in _TABLE["semantics"].items() if row.get("vouch_speaks"))

WARN_SPEAKS = frozenset(agent for agent, row in _TABLE["semantics"].items() if row.get("warn_speaks"))

VOUCH_NOTES = _TABLE["vouch_notes"]
