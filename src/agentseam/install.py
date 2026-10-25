"""Idempotent hook wiring: write our fragment into an agent's config, leave a witness."""

from __future__ import annotations

import os
import warnings

from . import adapters, install_legacy
from . import install_hook_dir as hook_dir
from .install_atomic import locked, refuse_escape
from .install_config import (
    BEGIN,
    END,
    MARKER,
    ConfigUnreadableError,
    apply_watch,
    bind_agent,
    check_line_safe,
    check_matcher,
    check_wireable,
    dump,
    fail_closed_kwarg,
    load,
    mark,
    merge,
    remove_block,
    resolve,
    strip,
    unwatched,
    write_block,
)
from .install_identity import installed

__all__ = ["BEGIN", "END", "MARKER", "ConfigUnreadableError", "config_path", "install", "installed", "uninstall"]


def config_path(agent, repo_root=".", owner="agentseam"):
    """Where this agent's hook config lives, resolved the way install resolves it."""
    return resolve(adapters.get(agent), repo_root, owner)


def _refuse_escapes(mod, path, repo_root):
    """Every file this agent's wiring would touch under the repo stays inside it; a home config is not the repo's."""
    if mod.CONFIG_PATH.startswith("~"):
        return
    refuse_escape(path, repo_root)
    for rel in getattr(mod, "LEGACY_CONFIG_PATHS", ()):
        refuse_escape(os.path.join(repo_root, rel), repo_root)


def install(agent, events, command, repo_root=".", matcher=None, owner="agentseam", fail_closed=None, watch=None):
    """Wire `command` for `events` into `agent`'s config, bound to `agent`. Returns the path written."""
    mod = adapters.get(agent)
    check_line_safe(command=command, owner=owner)
    command = bind_agent(command, agent)
    check_wireable(mod, agent, events)
    check_matcher(mod, agent, matcher)
    events, why = unwatched(mod, agent, events, watch)
    if why and not events:
        raise ValueError(why)
    if why:
        warnings.warn(why, UserWarning, stacklevel=2)
    extra = fail_closed_kwarg(mod, fail_closed)
    path = resolve(mod, repo_root, owner)
    _refuse_escapes(mod, path, repo_root)
    if getattr(mod, "CONFIG_FORMAT", "json") == "hook_dir":
        hook_dir.write(path, mod.hook_config(events, command, matcher=matcher, **extra), owner)
        return path
    if getattr(mod, "CONFIG_FORMAT", "json") == "toml":
        write_block(path, mod.render_config(mod.hook_config(events, command, matcher=matcher, **extra)), owner)
        return path
    fragment = mark(apply_watch(mod, mod.hook_config(events, command, matcher=matcher, **extra), watch), owner)
    with locked(path):
        install_legacy.check_not_shadowing(mod, agent, path, repo_root, owner)
        legacy = install_legacy.prepare_clean(mod, repo_root, owner)
        dump(path, merge(strip(load(path), owner), fragment))
    for legacy_path, after in legacy:
        dump(legacy_path, after)
    return path


def uninstall(agent, repo_root=".", owner="agentseam"):
    """Remove only our entries. Returns True when the file changed."""
    mod = adapters.get(agent)
    path = resolve(mod, repo_root, owner)
    _refuse_escapes(mod, path, repo_root)
    legacy_changed = install_legacy.clean(mod, repo_root, owner)
    if not os.path.exists(path):
        return legacy_changed
    if getattr(mod, "CONFIG_FORMAT", "json") == "hook_dir":
        return hook_dir.remove(path, mod.REVERSE_EVENT_MAP.values(), owner)
    if getattr(mod, "CONFIG_FORMAT", "json") == "toml":
        return remove_block(path, owner)
    with locked(path):
        before = load(path)
        after = strip(before, owner)
        if after == before:
            return legacy_changed
        dump(path, after)
    return True
