"""Per-agent capability data. Declaring what an agent can do is a different activity"""

from __future__ import annotations

from ._data import load

MATRIX = load("matrix.json")


from .matrix_gaps import GAPS  # noqa: E402  (below MATRIX so the import resolves)

MATRIX.update(GAPS)
