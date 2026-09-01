"""Load a vendor data table from data/*.json in the shape the code expects."""

from __future__ import annotations

import json
import os

_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")


def load(name):
    """The table in `data/<name>`, with every JSON array restored to a tuple.

    The tables held tuples when they were Python literals and nothing in them was ever a
    list, so array-to-tuple is an exact inverse rather than a guess. It matters because
    `(1, 2) == [1, 2]` is False in Python: a table that came back as lists would compare
    unequal to every expectation written against it.
    """
    with open(os.path.join(_DIR, name), encoding="utf-8") as fh:
        return _tuples(json.load(fh))


def _tuples(node):
    if isinstance(node, dict):
        return {key: _tuples(value) for key, value in node.items()}
    if isinstance(node, list):
        return tuple(_tuples(value) for value in node)
    return node
