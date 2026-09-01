"""Per-agent capability data. Declaring what an agent can do is a different activity"""

from __future__ import annotations

from ._data import load

MATRIX = load("matrix.json")


from .matrix_gaps import GAPS  # noqa: E402  (below MATRIX so the import resolves)

MATRIX.update(GAPS)


def _mirror_rewrite_as_transform(matrix):
    """Add the ACS-named "transform" key to every cell, mirroring "rewrite" (plan §1.6)."""
    for row in matrix.values():
        for cell in row["events"].values():
            cell.setdefault("transform", cell["rewrite"])


_mirror_rewrite_as_transform(MATRIX)
