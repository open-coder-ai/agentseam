"""`installed()`: is our hook wired -- and, opt-in, does it still match what we'd write today."""

from __future__ import annotations

import os

from . import adapters
from .install_config import (
    BEGIN,
    END,
    MARKER,
    ConfigUnreadableError,
    block_bounds,
    check_wireable,
    fail_closed_kwarg,
    load,
    mark,
    resolve,
)


def _owns_anything(obj, owner):
    """True when some entry carries OUR marker -- not merely our name somewhere in the file."""
    if isinstance(obj, dict):
        if obj.get(MARKER) == owner:
            return True
        return any(_owns_anything(v, owner) for v in obj.values())
    if isinstance(obj, list):
        return any(_owns_anything(v, owner) for v in obj)
    return False


def _owned_items(obj, owner):
    """Every list-item dict OUR marker was placed on, walked the same way `mark` places it."""
    items = []
    if isinstance(obj, dict):
        for v in obj.values():
            items.extend(_owned_items(v, owner))
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, dict) and v.get(MARKER) == owner:
                items.append(v)
            items.extend(_owned_items(v, owner))
    return items


_CONTENT_MODE_NEEDS_BOTH = "content-comparison mode needs both events and command"


def _installed_toml(mod, path, owner, content_mode, fragment):
    """`fragment` is the entry's hook_config() result, already built when content_mode."""
    if not os.path.exists(path):
        return False
    try:
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
    except (OSError, UnicodeError):
        return False
    bounds = block_bounds(text, owner)
    if bounds is None:
        return False
    if not content_mode:
        return True
    expected = "%s %s\n%s%s %s" % (BEGIN, owner, mod.render_config(fragment), END, owner)
    return text[bounds[0] : bounds[1]] == expected


def _installed_json(path, owner, content_mode, fragment):
    try:
        loaded = load(path)
    except ConfigUnreadableError:
        return False
    if not content_mode:
        return _owns_anything(loaded, owner)
    expected_items = _owned_items(mark(fragment, owner), owner)
    if not expected_items:
        return False
    actual_items = _owned_items(loaded, owner)
    return all(item in actual_items for item in expected_items)


def installed(agent, repo_root=".", owner="agentseam", events=None, command=None, matcher=None, fail_closed=None):
    """True when our witness is present in this agent's config."""
    mod = adapters.get(agent)
    path = resolve(mod, repo_root, owner)
    content_mode = events is not None or command is not None
    if content_mode and (events is None or command is None):
        raise ValueError(_CONTENT_MODE_NEEDS_BOTH)
    fragment = None
    if content_mode:
        check_wireable(mod, agent, events)
        extra = fail_closed_kwarg(mod, fail_closed)
        fragment = mod.hook_config(events, command, matcher=matcher, **extra)
    if getattr(mod, "CONFIG_FORMAT", "json") == "toml":
        return _installed_toml(mod, path, owner, content_mode, fragment)
    return _installed_json(path, owner, content_mode, fragment)
