"""Idempotent hook wiring: write our fragment into an agent's config, leave a witness."""

from __future__ import annotations

import os

from . import adapters
from .install_config import (
    BEGIN,
    END,
    MARKER,
    ConfigUnreadable,
    check_wireable,
    dump,
    fail_closed_kwarg,
    load,
    mark,
    merge,
    remove_block,
    resolve,
    strip_owned,
    write_block,
)
from .install_identity import installed

__all__ = ["BEGIN", "END", "MARKER", "ConfigUnreadable", "config_path", "install", "installed", "uninstall"]


def config_path(agent, repo_root=".", owner="agentseam"):
    """Where this agent's hook config lives, resolved the way install resolves it."""
    return resolve(adapters.get(agent), repo_root, owner)


def install(agent, events, command, repo_root=".", matcher=None, owner="agentseam", fail_closed=None):
    """Wire `command` for `events` into `agent`'s config. Returns the path written."""
    mod = adapters.get(agent)
    check_wireable(mod, agent, events)
    extra = fail_closed_kwarg(mod, fail_closed)
    path = resolve(mod, repo_root, owner)
    if getattr(mod, "CONFIG_FORMAT", "json") == "toml":
        write_block(path, mod.render_config(mod.hook_config(events, command, matcher=matcher, **extra)), owner)
        return path
    existing = strip_owned(load(path), owner)
    fragment = mark(mod.hook_config(events, command, matcher=matcher, **extra), owner)
    dump(path, merge(existing, fragment))
    return path


def uninstall(agent, repo_root=".", owner="agentseam"):
    """Remove only our entries. Returns True when the file changed."""
    mod = adapters.get(agent)
    path = resolve(mod, repo_root, owner)
    if not os.path.exists(path):
        return False
    if getattr(mod, "CONFIG_FORMAT", "json") == "toml":
        return remove_block(path, owner)
    before = load(path)
    after = strip_owned(before, owner)
    if after == before:
        return False
    dump(path, after)
    return True
