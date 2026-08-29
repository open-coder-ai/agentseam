"""Idempotent hook wiring: write our fragment into an agent's config, leave a witness.

Ownership discipline (learned the hard way by a sibling policy engine that shipped this
pattern first): every entry we add is marked, so uninstall removes exactly ours and never
a user's own hooks, and a re-install replaces rather than duplicates.

`installed()` lives in `install_identity.py` (a query is a different activity from a
write) and is re-exported below -- `agentseam.install.installed` is unchanged for every
existing caller.
"""

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

__all__ = ["BEGIN", "END", "ConfigUnreadable", "MARKER", "config_path", "install", "installed", "uninstall"]


def config_path(agent, repo_root=".", owner="agentseam"):
    """Where this agent's hook config lives, resolved the way install resolves it.

    Exposed because callers keep needing the answer -- a tool reporting what is wired has to
    name the file -- and re-deriving it from CONFIG_PATH loses the `~` and `*` handling that
    `resolve` already gets right.
    """
    return resolve(adapters.get(agent), repo_root, owner)


def install(agent, events, command, repo_root=".", matcher=None, owner="agentseam", fail_closed=None):
    """Wire `command` for `events` into `agent`'s config. Returns the path written.

    Raises ValueError for an event this agent cannot be wired for, rather than writing a
    config that quietly omits it. Asking to gate an event and getting a silent no-op is the
    failure this library exists to prevent, so it must not be how its own installer behaves.
    """
    mod = adapters.get(agent)
    check_wireable(mod, agent, events)
    extra = fail_closed_kwarg(mod, fail_closed)
    path = resolve(mod, repo_root, owner)  # e.g. .github/hooks/*.json
    if getattr(mod, "CONFIG_FORMAT", "json") == "toml":
        write_block(path, mod.render_config(mod.hook_config(events, command, matcher=matcher, **extra)), owner)
        return path
    existing = strip_owned(load(path), owner)  # idempotent: drop our old entries
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
