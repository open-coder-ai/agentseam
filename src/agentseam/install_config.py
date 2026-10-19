"""Idempotent-wiring plumbing shared by `install` (writes) and `install_identity` (queries)."""

from __future__ import annotations

import inspect
import json
import os

from .install_atomic import locked, write_text

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
        raise ConfigUnreadableError(
            "%s exists but is not UTF-8 text (%s); refusing to overwrite it." % (path, exc)
        ) from exc
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
    """Keys in the file's own order: a re-sorted file is a diff of the user's that nobody asked for."""
    write_text(path, json.dumps(data, indent=2) + "\n")


def read_text(path):
    """The file as text, decoded as the UTF-8 both config formats are specified in -- never
    as the platform locale, which on Windows is a code page that cannot hold it."""
    try:
        with open(path, encoding="utf-8-sig", newline="") as fh:
            return fh.read()
    except UnicodeError as exc:
        raise ConfigUnreadableError(
            "%s exists but is not UTF-8 text (%s); refusing to overwrite it." % (path, exc)
        ) from exc


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


def strip(obj, owner):
    """`obj` without `owner`'s entries, and without the lists and objects that removal emptied."""
    return _prune_emptied(obj, strip_owned(obj, owner))


def _prune_emptied(before, after):
    if not (isinstance(before, dict) and isinstance(after, dict)):
        return after
    out = {}
    for key, value in after.items():
        kept = _prune_emptied(before.get(key), value)
        if isinstance(kept, (list, dict)) and not kept and before.get(key):
            continue
        out[key] = kept
    return out


def merge(base, addition, where=()):
    """Fold `addition` into `base`; a container where the user's file holds something else refuses."""
    for key, value in addition.items():
        current = base.get(key)
        if isinstance(value, dict) and isinstance(current, dict):
            merge(current, value, (*where, key))
        elif isinstance(value, list) and isinstance(current, list):
            current.extend(value)
        elif isinstance(value, (dict, list)) and current is not None:
            raise ConfigUnreadableError(
                "%s in the existing config is a %s, not a %s; refusing to overwrite it."
                % (".".join((*where, key)), type(current).__name__, type(value).__name__)
            )
        else:
            base[key] = value
    return base


def _find_line(text, line, start=0):
    """Offset of `line` occupying a whole line of `text`, or -1. A marker that is only a
    prefix of a longer one (owner `chock` inside `chock-java-security`'s), or quoted inside a
    comment, is somebody else's."""
    pos = text.find(line, start)
    while pos != -1:
        stop = pos + len(line)
        if (pos == 0 or text[pos - 1] == "\n") and (stop == len(text) or text[stop] in "\r\n"):
            return pos
        pos = text.find(line, pos + 1)
    return -1


def block_bounds(text, owner):
    begin, end = "%s %s" % (BEGIN, owner), "%s %s" % (END, owner)
    start = _find_line(text, begin)
    stop = _find_line(text, end, start) if start != -1 else -1
    if stop == -1:
        return None
    return start, stop + len(end)


def _newline_of(text):
    return "\r\n" if "\r\n" in text else "\n"


def render_block(path, body, owner):
    """The text of `path` with our block replaced or appended. Everything outside it is left
    byte-for-byte, and the block takes the file's own line endings so a Windows-authored file
    stays one kind."""
    text = read_text(path) if os.path.exists(path) else ""
    nl = _newline_of(text)
    block = ("%s %s\n%s%s %s" % (BEGIN, owner, body, END, owner)).replace("\n", nl)
    bounds = block_bounds(text, owner)
    if bounds:
        return text[: bounds[0]] + block + text[bounds[1] :]
    return (text.rstrip("\r\n") + nl + nl if text.strip() else "") + block + nl


def write_block(path, body, owner, mode=None):
    with locked(path):
        write_text(path, render_block(path, body, owner), mode)


def strip_block(path, owner):
    """Remove our block from `path` without taking the lock. Returns True when one was there."""
    text = read_text(path)
    bounds = block_bounds(text, owner)
    if not bounds:
        return False
    nl = _newline_of(text)
    cleaned = (text[: bounds[0]].rstrip("\r\n") + nl + text[bounds[1] :].lstrip("\r\n")).strip("\r\n")
    write_text(path, cleaned + nl if cleaned else "")
    return True


def remove_block(path, owner):
    with locked(path):
        return strip_block(path, owner)


def bind_agent(command, agent):
    """`command` with `agent`'s name as its last argument -- what `dispatch.bound_agent()` reads,
    so an installed hook answers in its agent's dialect without guessing it from the payload.
    A command already ending in the name (tools/capture.py's probe) is left as it is."""
    command = command.rstrip()
    return command if command.split()[-1:] == [agent] else "%s %s" % (command, agent)


def resolve(mod, repo_root, owner):
    """Where this agent's config lives. A `*` in the adapter's own CONFIG_PATH is the owner's
    slot; one in `repo_root` or the user's home is just a character in a directory name."""
    config = mod.CONFIG_PATH.replace("*", owner)
    return os.path.expanduser(config) if config.startswith("~") else os.path.join(repo_root, config)


def fail_closed_kwarg(mod, fail_closed):
    """`{"fail_closed": ...}` when this adapter's `hook_config` takes it, else `{}`."""
    if fail_closed is not None and "fail_closed" in inspect.signature(mod.hook_config).parameters:
        return {"fail_closed": fail_closed}
    return {}


def _watch_list_events(mod):
    return getattr(mod, "CONFIG", {}).get("hook_entry", {}).get("watch_list_events", ())


def unwatched(mod, agent, events, watch):
    """`(events to wire, why the rest are not)`: an event whose matcher is the vendor's watch
    list of literal file names can never fire with no list, so it is left out, never claimed."""
    if watch:
        bad = [name for name in watch if not isinstance(name, str) or not name or "|" in name]
        if bad:
            raise ValueError("watch names literal files, one per item, without '|': %r" % (bad,))
        return list(events), None
    left_out = [e for e in events if e in _watch_list_events(mod)]
    if not left_out:
        return list(events), None
    why = (
        "%s not wired for %s: it watches only the literal file names its matcher lists, and starts no "
        "watcher without one; pass watch=[...] (--watch FILE) to wire it" % (", ".join(left_out), agent)
    )
    return [e for e in events if e not in left_out], why


def apply_watch(mod, fragment, watch):
    """Write the watch list as the matcher of each watch-list event's entry, '|'-joined."""
    if not watch:
        return fragment
    table = fragment.get("hooks", fragment)
    for ev in _watch_list_events(mod):
        for entry in table.get(mod.REVERSE_EVENT_MAP.get(ev), ()):
            entry["matcher"] = "|".join(watch)
    return fragment


def check_wireable(mod, agent, events):
    """Raise ValueError naming exactly what `agent` cannot be wired for, or do nothing."""
    unwireable = [e for e in events if e not in getattr(mod, "REVERSE_EVENT_MAP", {})]
    if unwireable:
        raise ValueError(
            "%s has no hook for: %s (it can be wired for: %s)"
            % (agent, ", ".join(sorted(unwireable)), ", ".join(sorted(mod.REVERSE_EVENT_MAP)))
        )


def check_matcher(mod, agent, matcher):
    """Raise ValueError when `matcher` is given for an agent whose hook config has no matcher."""
    if matcher and not getattr(mod, "CONFIG", {}).get("hook_entry", {}).get("matcher"):
        raise ValueError(
            "%s has no tool matcher, so --matcher %r would be dropped and the hook would run on every tool"
            % (agent, matcher)
        )
