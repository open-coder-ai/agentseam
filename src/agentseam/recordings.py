"""Frozen witness recordings: data the package reads, never writes.

A recording under ``data/recordings/<agent>@<version>.json`` is what
``tools/experiment.py --record`` freezes from a real agent run (``tools/recorded_driver.py``,
a dev-only tool). Reading it back -- so ``--driver recorded``, ``tools/watch_versions.py`` and
``agentseam matrix --evidence`` all agree on what is on disk -- belongs in the installed,
stdlib-only package instead, the same split every other data table in this repo follows.
"""

from __future__ import annotations

import os
import re

from ._data import load
from .staleness import parse_version

_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
RECORDINGS_DIR = os.path.join(_DATA_DIR, "recordings")
_FILENAME_RE = re.compile(r"^([a-z][a-z0-9_]*)@(.+)\.json$")


def _recording_files():
    if not os.path.isdir(RECORDINGS_DIR):
        return []
    return sorted(name for name in os.listdir(RECORDINGS_DIR) if _FILENAME_RE.match(name))


def versions(agent):
    """Every version recorded for `agent`, oldest first."""
    found = (_FILENAME_RE.match(name) for name in _recording_files())
    return sorted((m.group(2) for m in found if m and m.group(1) == agent), key=parse_version)


def latest_version(agent):
    """The newest recorded version for `agent`, or None if it has never been witnessed."""
    found = versions(agent)
    return found[-1] if found else None


def path_for(agent, version):
    """Where `agent`'s recording at `version` lives, whether or not it exists yet."""
    return os.path.join(RECORDINGS_DIR, "%s@%s.json" % (agent, version))


def load_recording(agent, version=None):
    """The recording body for `agent` at `version` (default: its latest), or None."""
    version = version or latest_version(agent)
    if version is None:
        return None
    relative = "recordings/%s@%s.json" % (agent, version)
    if not os.path.exists(os.path.join(_DATA_DIR, relative)):
        return None
    return load(relative)


__all__ = ["RECORDINGS_DIR", "latest_version", "load_recording", "path_for", "versions"]
