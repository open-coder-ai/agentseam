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


def installed(agent, repo_root=".", owner="agentseam", events=None, command=None, matcher=None, fail_closed=None):
    """True when our witness is present in this agent's config."""
    mod = adapters.get(agent)
    path = resolve(mod, repo_root, owner)
    content_mode = events is not None or command is not None
    if content_mode and (events is None or command is None):
        raise ValueError(_CONTENT_MODE_NEEDS_BOTH)
    extra = {}
    if content_mode:
        check_wireable(mod, agent, events)
        extra = fail_closed_kwarg(mod, fail_closed)
    if getattr(mod, "CONFIG_FORMAT", "json") == "toml":
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
        expected = "%s %s\n%s%s %s" % (
            BEGIN,
            owner,
            mod.render_config(mod.hook_config(events, command, matcher=matcher, **extra)),
            END,
            owner,
        )
        return text[bounds[0] : bounds[1]] == expected
    try:
        loaded = load(path)
    except ConfigUnreadableError:
        return False
    if not content_mode:
        return _owns_anything(loaded, owner)
    expected_items = _owned_items(mark(mod.hook_config(events, command, matcher=matcher, **extra), owner), owner)
    if not expected_items:
        return False
    actual_items = _owned_items(loaded, owner)
    return all(item in actual_items for item in expected_items)
