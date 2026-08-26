"""Idempotent hook wiring: write our fragment into an agent's config, leave a witness.

Ownership discipline (borrowed from chock, which learned it the hard way): every entry
we add is marked, so uninstall removes exactly ours and never a user's own hooks, and a
re-install replaces rather than duplicates.
"""

from __future__ import annotations

import json
import os

from . import adapters

MARKER = "_agentshim"


def _load(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path) as fh:
            return json.load(fh)
    except (ValueError, OSError):
        return {}


def _dump(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _mark(obj, owner):
    """Tag every hook entry we own so uninstall is surgical."""
    if isinstance(obj, dict):
        if "command" in obj or "hooks" in obj:
            obj[MARKER] = owner
        for v in obj.values():
            _mark(v, owner)
    elif isinstance(obj, list):
        for v in obj:
            _mark(v, owner)
    return obj


def _strip_owned(obj, owner):
    """Remove entries we own; leave everything else untouched."""
    if isinstance(obj, list):
        return [_strip_owned(v, owner) for v in obj
                if not (isinstance(v, dict) and v.get(MARKER) == owner)]
    if isinstance(obj, dict):
        return {k: _strip_owned(v, owner) for k, v in obj.items() if k != MARKER}
    return obj


def _merge(base, addition):
    for key, value in addition.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        elif isinstance(value, list) and isinstance(base.get(key), list):
            base[key].extend(value)
        else:
            base[key] = value
    return base


def install(agent, events, command, repo_root=".", matcher=None, owner="agentshim"):
    """Wire `command` for `events` into `agent`'s config. Returns the path written."""
    mod = adapters.get(agent)
    path = os.path.join(repo_root, mod.CONFIG_PATH)
    if "*" in path:                      # e.g. .github/hooks/*.json
        path = path.replace("*", owner)
    existing = _strip_owned(_load(path), owner)      # idempotent: drop our old entries
    fragment = _mark(mod.hook_config(events, command, matcher=matcher), owner)
    _dump(path, _merge(existing, fragment))
    return path


def uninstall(agent, repo_root=".", owner="agentshim"):
    """Remove only our entries. Returns True when the file changed."""
    mod = adapters.get(agent)
    path = os.path.join(repo_root, mod.CONFIG_PATH)
    if "*" in path:
        path = path.replace("*", owner)
    if not os.path.exists(path):
        return False
    before = _load(path)
    after = _strip_owned(before, owner)
    if after == before:
        return False
    _dump(path, after)
    return True


def installed(agent, repo_root=".", owner="agentshim"):
    """True when our witness is present in this agent's config."""
    mod = adapters.get(agent)
    path = os.path.join(repo_root, mod.CONFIG_PATH)
    if "*" in path:
        path = path.replace("*", owner)
    return owner in json.dumps(_load(path))
