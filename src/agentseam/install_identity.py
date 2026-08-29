"""`installed()`: is our hook wired -- and, opt-in, does it still match what we'd write today.

Split out of `install.py` (that module writes; this one only answers questions) so both
stay under the file-size convention. Public API is unchanged: `agentseam.install.installed`
is this module's `installed`, re-exported for every existing caller.
"""

from __future__ import annotations

import os

from . import adapters
from .install_config import (
    BEGIN,
    END,
    MARKER,
    ConfigUnreadable,
    block_bounds,
    check_wireable,
    fail_closed_kwarg,
    load,
    mark,
    resolve,
)


def _owns_anything(obj, owner):
    """True when some entry carries OUR marker -- not merely our name somewhere in the file.

    The witness used to be `owner in json.dumps(...)`, a substring test over the whole
    serialised config. Antigravity's config group is literally named "agentseam", the
    default owner, so after uninstall the leftover empty group `{"agentseam": {...}}` kept
    the witness True forever: `installed()` reported a guard that was gone. Any user string
    containing the owner name did the same -- a path, a command, a comment.

    Looking for the marker key with our value is the question we actually meant to ask.
    """
    if isinstance(obj, dict):
        if obj.get(MARKER) == owner:
            return True
        return any(_owns_anything(v, owner) for v in obj.values())
    if isinstance(obj, list):
        return any(_owns_anything(v, owner) for v in obj)
    return False


def _owned_items(obj, owner):
    """Every list-item dict OUR marker was placed on, walked the same way `mark` places it.

    `mark` only tags a dict reached as a LIST ITEM (see its docstring) -- that is where
    every adapter's owned entries actually live. Collecting exactly those, rather than the
    whole owned subtree, is what makes a content comparison possible: two configs can wrap
    the same owned entries in different surrounding structure (key order, a sibling group a
    user added) and still be the same install.
    """
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


def installed(agent, repo_root=".", owner="agentseam", events=None, command=None, matcher=None, fail_closed=None):
    """True when our witness is present in this agent's config.

    Default mode (`events`/`command` omitted) answers a presence question: does some entry
    here carry our marker at all. Right for a single-command consumer, where "we wrote
    this" is the only thing that ever needs to be true -- and it is what `install()`'s own
    unconditional overwrite-on-reinstall keeps trivially in sync.

    Content-comparison mode -- opt in by passing the same `events`/`command`/`matcher`
    (`fail_closed` too, where the adapter takes it) `install()` would use to render the
    fragment RIGHT NOW -- answers a stronger question: does the INSTALLED content still
    match the CURRENTLY-COMPILED one. A multi-fragment consumer (each hook independently
    toggleable, e.g. one entry per policy id) cannot use marker-presence for this: a stale
    hook whose guard has since changed would go on reading as "installed" -- silently
    keeping a coverage claim for a guard that no longer matches what is actually wired. A
    real historical bug of exactly that shape is why an `installed_pretooluse_policy_ids`-
    style caller needs this. A changed fragment reads as not-installed here; the caller
    re-syncs by calling `install()` again, which converges (idempotent, matching the default
    mode).
    """
    mod = adapters.get(agent)
    path = resolve(mod, repo_root, owner)
    content_mode = events is not None or command is not None
    if content_mode and (events is None or command is None):
        raise ValueError("content-comparison mode needs both events and command")
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
            # A query never raises: an unreadable or non-UTF-8 file means our witness is not
            # known to be there. This mirrors the JSON branch's ConfigUnreadable handling;
            # uninstall() is where an unreadable file must stop, not here.
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
    except ConfigUnreadable:
        # A query never raises: if the file cannot be read, our witness is not known to be
        # there. uninstall() is where an unreadable file must stop, not here.
        return False
    if not content_mode:
        return _owns_anything(loaded, owner)
    expected_items = _owned_items(mark(mod.hook_config(events, command, matcher=matcher, **extra), owner), owner)
    if not expected_items:
        return False
    actual_items = _owned_items(loaded, owner)
    return all(item in actual_items for item in expected_items)
