"""Idempotent hook wiring: write our fragment into an agent's config, leave a witness.

Ownership discipline (borrowed from chock, which learned it the hard way): every entry
we add is marked, so uninstall removes exactly ours and never a user's own hooks, and a
re-install replaces rather than duplicates.
"""

from __future__ import annotations

import json
import os

from . import adapters

MARKER = "_agentseam"

# TOML configs are the user's whole settings document rather than a hooks file, and the
# stdlib can read TOML but not write it. So those get the treatment instruction files
# already use: a marker-delimited block we own, with every byte outside it preserved.
BEGIN = "# >>> agentseam >>>"
END = "# <<< agentseam <<<"


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
        return [_strip_owned(v, owner) for v in obj if not (isinstance(v, dict) and v.get(MARKER) == owner)]
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


def _block_bounds(text, owner):
    begin, end = "%s %s" % (BEGIN, owner), "%s %s" % (END, owner)
    start, stop = text.find(begin), text.find(end)
    if start == -1 or stop == -1 or stop < start:
        return None
    return start, stop + len(end)


def _write_block(path, body, owner):
    """Replace our block, or append one. Everything outside it is left byte-for-byte."""
    text = ""
    if os.path.exists(path):
        with open(path) as fh:
            text = fh.read()
    block = "%s %s\n%s%s %s" % (BEGIN, owner, body, END, owner)
    bounds = _block_bounds(text, owner)
    if bounds:
        text = text[: bounds[0]] + block + text[bounds[1] :]
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block + "\n"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def _remove_block(path, owner):
    with open(path) as fh:
        text = fh.read()
    bounds = _block_bounds(text, owner)
    if not bounds:
        return False
    cleaned = (text[: bounds[0]].rstrip("\n") + "\n" + text[bounds[1] :].lstrip("\n")).strip("\n")
    with open(path, "w") as fh:
        fh.write(cleaned + "\n" if cleaned else "")
    return True


def _resolve(mod, repo_root, owner):
    """Where this agent's config lives.

    A CONFIG_PATH beginning with `~` is user-scoped and deliberately so -- Junie ignores
    hooks from a repository-controlled config, so a project file there would never fire.
    Joining it under repo_root produced a literal `./~/` directory: a config written
    somewhere no agent reads, indistinguishable at capture time from a vendor whose hooks
    do not work.
    """
    config = mod.CONFIG_PATH
    path = os.path.expanduser(config) if config.startswith("~") else os.path.join(repo_root, config)
    return path.replace("*", owner) if "*" in path else path


def install(agent, events, command, repo_root=".", matcher=None, owner="agentseam"):
    """Wire `command` for `events` into `agent`'s config. Returns the path written.

    Raises ValueError for an event this agent cannot be wired for, rather than writing a
    config that quietly omits it. Asking to gate an event and getting a silent no-op is the
    failure this library exists to prevent, so it must not be how its own installer behaves.
    """
    mod = adapters.get(agent)
    unwireable = [e for e in events if e not in getattr(mod, "REVERSE_EVENT_MAP", {})]
    if unwireable:
        raise ValueError(
            "%s has no hook for: %s (it can be wired for: %s)"
            % (agent, ", ".join(sorted(unwireable)), ", ".join(sorted(mod.REVERSE_EVENT_MAP)))
        )
    path = _resolve(mod, repo_root, owner)  # e.g. .github/hooks/*.json
    if getattr(mod, "CONFIG_FORMAT", "json") == "toml":
        _write_block(path, mod.render_config(mod.hook_config(events, command, matcher=matcher)), owner)
        return path
    existing = _strip_owned(_load(path), owner)  # idempotent: drop our old entries
    fragment = _mark(mod.hook_config(events, command, matcher=matcher), owner)
    _dump(path, _merge(existing, fragment))
    return path


def uninstall(agent, repo_root=".", owner="agentseam"):
    """Remove only our entries. Returns True when the file changed."""
    mod = adapters.get(agent)
    path = _resolve(mod, repo_root, owner)
    if not os.path.exists(path):
        return False
    if getattr(mod, "CONFIG_FORMAT", "json") == "toml":
        return _remove_block(path, owner)
    before = _load(path)
    after = _strip_owned(before, owner)
    if after == before:
        return False
    _dump(path, after)
    return True


def installed(agent, repo_root=".", owner="agentseam"):
    """True when our witness is present in this agent's config."""
    mod = adapters.get(agent)
    path = _resolve(mod, repo_root, owner)
    if getattr(mod, "CONFIG_FORMAT", "json") == "toml":
        if not os.path.exists(path):
            return False
        with open(path) as fh:
            return _block_bounds(fh.read(), owner) is not None
    return owner in json.dumps(_load(path))
