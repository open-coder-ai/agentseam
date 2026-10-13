"""The hook configs an agent still reads as a fallback: cleaned on install and uninstall."""

from __future__ import annotations

import os

from .install_config import dump, load, strip


def _legacy_paths(mod, repo_root):
    return [os.path.join(repo_root, rel) for rel in getattr(mod, "LEGACY_CONFIG_PATHS", ())]


def _defines_hooks(data):
    hooks = data.get("hooks")
    return isinstance(hooks, dict) and any(hooks.values())


def check_not_shadowing(mod, agent, path, repo_root, owner):
    """Raise ValueError when writing `path` would switch off the user's own hooks in a legacy file.

    The vendor reads the legacy file only while `path` defines no hooks, so ours there would
    silently replace theirs.
    """
    if os.path.exists(path) and _defines_hooks(load(path)):
        return
    for legacy in _legacy_paths(mod, repo_root):
        if os.path.exists(legacy) and _defines_hooks(strip(load(legacy), owner)):
            raise ValueError(
                "%s reads %s only while %s defines no hooks, so wiring ours there would switch off "
                "the hooks already in %s; move them into %s, then re-run" % (agent, legacy, path, legacy, path)
            )


def clean(mod, repo_root, owner):
    """Strip `owner`'s entries from every legacy file. Returns True when one changed."""
    changed = False
    for legacy in _legacy_paths(mod, repo_root):
        if not os.path.exists(legacy):
            continue
        before = load(legacy)
        after = strip(before, owner)
        if after != before:
            dump(legacy, after)
            changed = True
    return changed
