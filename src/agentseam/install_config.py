"""Idempotent-wiring plumbing shared by `install` (writes) and `install_identity` (queries)."""

from __future__ import annotations

import inspect
import json
import os

MARKER = "_agentseam"

BEGIN = "# >>> agentseam >>>"
END = "# <<< agentseam <<<"


class ConfigUnreadableError(Exception):
    """An existing config file could not be read or parsed, so it must not be overwritten."""


def load(path):
    """The existing config as a dict. {} only when the file is genuinely absent."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
    except OSError as exc:
        raise ConfigUnreadableError("cannot read %s: %s" % (path, exc)) from exc
    except UnicodeError as exc:
        raise ConfigUnreadableError("%s exists but is not UTF-8 text (%s); refusing to overwrite it." % (path, exc)) from exc
    if not text.strip():
        return {}
    try:
        loaded = json.loads(text)
    except ValueError as exc:
        raise ConfigUnreadableError(
            "%s exists but is not valid JSON (%s); refusing to overwrite it. "
            "Fix or move the file, then re-run." % (path, exc)
        ) from exc
    if not isinstance(loaded, dict):
        raise ConfigUnreadableError("%s is valid JSON but not an object; refusing to overwrite it." % path)
    return loaded


def dump(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def mark(obj, owner):
    """Tag every hook entry we own so uninstall is surgical."""
    if isinstance(obj, dict):
        for v in obj.values():
            mark(v, owner)
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, dict):
                v[MARKER] = owner
            mark(v, owner)
    return obj


def strip_owned(obj, owner):
    """Remove entries `owner` owns; leave everything else untouched -- including its marker."""
    if isinstance(obj, list):
        return [strip_owned(v, owner) for v in obj if not (isinstance(v, dict) and v.get(MARKER) == owner)]
    if isinstance(obj, dict):
        return {k: strip_owned(v, owner) for k, v in obj.items() if not (k == MARKER and v == owner)}
    return obj


def merge(base, addition):
    for key, value in addition.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            merge(base[key], value)
        elif isinstance(value, list) and isinstance(base.get(key), list):
            base[key].extend(value)
        else:
            base[key] = value
    return base


def block_bounds(text, owner):
    begin, end = "%s %s" % (BEGIN, owner), "%s %s" % (END, owner)
    start, stop = text.find(begin), text.find(end)
    if start == -1 or stop == -1 or stop < start:
        return None
    return start, stop + len(end)


def write_block(path, body, owner):
    """Replace our block, or append one. Everything outside it is left byte-for-byte."""
    text = ""
    if os.path.exists(path):
        with open(path) as fh:
            text = fh.read()
    block = "%s %s\n%s%s %s" % (BEGIN, owner, body, END, owner)
    bounds = block_bounds(text, owner)
    if bounds:
        text = text[: bounds[0]] + block + text[bounds[1] :]
    else:
        text = (text.rstrip("\n") + "\n\n" if text.strip() else "") + block + "\n"
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as fh:
        fh.write(text)


def remove_block(path, owner):
    with open(path) as fh:
        text = fh.read()
    bounds = block_bounds(text, owner)
    if not bounds:
        return False
    cleaned = (text[: bounds[0]].rstrip("\n") + "\n" + text[bounds[1] :].lstrip("\n")).strip("\n")
    with open(path, "w") as fh:
        fh.write(cleaned + "\n" if cleaned else "")
    return True


def resolve(mod, repo_root, owner):
    """Where this agent's config lives."""
    config = mod.CONFIG_PATH
    path = os.path.expanduser(config) if config.startswith("~") else os.path.join(repo_root, config)
    return path.replace("*", owner) if "*" in path else path


def fail_closed_kwarg(mod, fail_closed):
    """`{"fail_closed": ...}` when this adapter's `hook_config` takes it, else `{}`."""
    if fail_closed is not None and "fail_closed" in inspect.signature(mod.hook_config).parameters:
        return {"fail_closed": fail_closed}
    return {}


def check_wireable(mod, agent, events):
    """Raise ValueError naming exactly what `agent` cannot be wired for, or do nothing."""
    unwireable = [e for e in events if e not in getattr(mod, "REVERSE_EVENT_MAP", {})]
    if unwireable:
        raise ValueError(
            "%s has no hook for: %s (it can be wired for: %s)"
            % (agent, ", ".join(sorted(unwireable)), ", ".join(sorted(mod.REVERSE_EVENT_MAP)))
        )
