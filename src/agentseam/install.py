"""Idempotent hook wiring: write our fragment into an agent's config, leave a witness.

Ownership discipline (borrowed from chock, which learned it the hard way): every entry
we add is marked, so uninstall removes exactly ours and never a user's own hooks, and a
re-install replaces rather than duplicates.
"""

from __future__ import annotations

import inspect
import json
import os

from . import adapters

MARKER = "_agentseam"

# TOML configs are the user's whole settings document rather than a hooks file, and the
# stdlib can read TOML but not write it. So those get the treatment instruction files
# already use: a marker-delimited block we own, with every byte outside it preserved.
BEGIN = "# >>> agentseam >>>"
END = "# <<< agentseam <<<"


class ConfigUnreadable(Exception):
    """An existing config file could not be read or parsed, so it must not be overwritten.

    Returning {} here -- as this used to -- meant install merged its fragment into an empty
    object and wrote that back, silently DESTROYING everything the user had. For Junie, whose
    config.json is the whole CLI configuration rather than a hooks-only file, a single stray
    byte (a UTF-8 BOM, a trailing comma, a half-saved edit) cost the user their entire
    config. Wiping a file we cannot understand is the exact silent-destruction this library
    exists to refuse; the honest move is to stop and say so.
    """


def _load(path):
    """The existing config as a dict. {} only when the file is genuinely absent.

    A BOM is tolerated (utf-8-sig), mirroring the runtime's stdin fix -- Windows editors add
    one and it is not corruption. Anything still unparseable, or unreadable, raises rather
    than returning {}, because the caller is about to write this file back.
    """
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8-sig") as fh:
            text = fh.read()
    except OSError as exc:
        raise ConfigUnreadable("cannot read %s: %s" % (path, exc)) from exc
    except UnicodeError as exc:
        # A file that is not UTF-8/UTF-8-BOM (e.g. UTF-16) raises while decoding here. Wrap it
        # as ConfigUnreadable, like a JSON error, so it is preserved and reported through the
        # one path -- keeping the exception type consistent -- rather than crashing
        # install/uninstall, and installed()'s JSON branch (which catches only
        # ConfigUnreadable), with a raw UnicodeDecodeError.
        raise ConfigUnreadable("%s exists but is not UTF-8 text (%s); refusing to overwrite it." % (path, exc)) from exc
    if not text.strip():
        return {}  # an empty file is not corruption; treat it as a fresh config
    try:
        loaded = json.loads(text)
    except ValueError as exc:
        raise ConfigUnreadable(
            "%s exists but is not valid JSON (%s); refusing to overwrite it. "
            "Fix or move the file, then re-run." % (path, exc)
        ) from exc
    if not isinstance(loaded, dict):
        raise ConfigUnreadable("%s is valid JSON but not an object; refusing to overwrite it." % path)
    return loaded


def _dump(path, data):
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w") as fh:
        json.dump(data, fh, indent=2, sort_keys=True)
        fh.write("\n")


def _mark(obj, owner):
    """Tag every hook entry we own so uninstall is surgical.

    Only a dict reached as a LIST ITEM gets tagged -- that is where every adapter's owned
    entries actually live, whether that item is a leaf command object (cursor, windsurf) or a
    matcher/hooks group wrapping one (claude_code, junie, gemini_cli, grok, devin,
    antigravity, tabnine). The top-level container a caller passes in (`{"hooks": {...}}`,
    `{"version": 1, "hooks": [...]}`, `{GROUP: group}`) is reached by the initial call, not as
    a list item, so it is never tagged -- some vendors' hook-config parsers reject unknown
    top-level fields outright. Witnessed live installing here (Codex CLI, 2026-08-27):
    "unknown field `_agentseam`, expected `description` or `hooks`", which silently drops
    every hook in the file -- the whole file failed to load, not just our entry. A
    known-independently vendor bug, not a one-off: openai/codex#30397 documents Codex < 0.143.0
    rejecting the entire hooks file over an unexpected top-level `description` key the exact
    same way (fixed in #30229), which is why chock's own Codex emitter never writes one either.
    """
    if isinstance(obj, dict):
        for v in obj.values():
            _mark(v, owner)
    elif isinstance(obj, list):
        for v in obj:
            if isinstance(v, dict):
                v[MARKER] = owner
            _mark(v, owner)
    return obj


def _strip_owned(obj, owner):
    """Remove entries `owner` owns; leave everything else untouched -- including its marker.

    The dict branch used to drop MARKER unconditionally, which erased OTHER owners' marks.
    That is not cosmetic: ownership is the only thing that makes uninstall surgical, so a
    second `install(..., owner="b")` silently un-owned everything "a" had written, and
    neither could be uninstalled afterwards. Both sets of entries stayed in the user's real
    settings file with nothing left to identify them -- permanent pollution, from the one
    operation whose entire purpose is to be reversible.

    A marker equal to `owner` is still dropped here, for the dict that is not a list item
    and so cannot be removed by the branch above. `_mark` does not put one there today (see
    its docstring: some vendors reject unknown top-level fields), but stripping ours if it
    ever appears is the conservative half of the pair.
    """
    if isinstance(obj, list):
        return [_strip_owned(v, owner) for v in obj if not (isinstance(v, dict) and v.get(MARKER) == owner)]
    if isinstance(obj, dict):
        return {k: _strip_owned(v, owner) for k, v in obj.items() if not (k == MARKER and v == owner)}
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


def config_path(agent, repo_root=".", owner="agentseam"):
    """Where this agent's hook config lives, resolved the way install resolves it.

    Exposed because callers keep needing the answer -- a tool reporting what is wired has to
    name the file -- and re-deriving it from CONFIG_PATH loses the `~` and `*` handling that
    `_resolve` already gets right.
    """
    return _resolve(adapters.get(agent), repo_root, owner)


def install(agent, events, command, repo_root=".", matcher=None, owner="agentseam", fail_closed=None):
    """Wire `command` for `events` into `agent`'s config. Returns the path written.

    Raises ValueError for an event this agent cannot be wired for, rather than writing a
    config that quietly omits it. Asking to gate an event and getting a silent no-op is the
    failure this library exists to prevent, so it must not be how its own installer behaves.
    """
    mod = adapters.get(agent)
    # `fail_closed=False` marks this wiring as an OBSERVER, not a gate. It reaches only the
    # adapters whose hook_config takes the argument -- today just cursor, the one vendor
    # whose config carries a per-hook fail mode. Forwarded by signature rather than by name
    # so an adapter that grows the knob later gets it without a change here.
    #
    # It exists for the capture probe, which always allows: installed as a gate on Cursor it
    # inherits failClosed:true, so a probe that cannot launch BLOCKS the user's real command.
    # Verification that costs someone a broken session is not worth running.
    extra = {}
    if fail_closed is not None and "fail_closed" in inspect.signature(mod.hook_config).parameters:
        extra["fail_closed"] = fail_closed
    unwireable = [e for e in events if e not in getattr(mod, "REVERSE_EVENT_MAP", {})]
    if unwireable:
        raise ValueError(
            "%s has no hook for: %s (it can be wired for: %s)"
            % (agent, ", ".join(sorted(unwireable)), ", ".join(sorted(mod.REVERSE_EVENT_MAP)))
        )
    path = _resolve(mod, repo_root, owner)  # e.g. .github/hooks/*.json
    if getattr(mod, "CONFIG_FORMAT", "json") == "toml":
        _write_block(path, mod.render_config(mod.hook_config(events, command, matcher=matcher, **extra)), owner)
        return path
    existing = _strip_owned(_load(path), owner)  # idempotent: drop our old entries
    fragment = _mark(mod.hook_config(events, command, matcher=matcher, **extra), owner)
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


def installed(agent, repo_root=".", owner="agentseam"):
    """True when our witness is present in this agent's config."""
    mod = adapters.get(agent)
    path = _resolve(mod, repo_root, owner)
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
        return _block_bounds(text, owner) is not None
    try:
        return _owns_anything(_load(path), owner)
    except ConfigUnreadable:
        # A query never raises: if the file cannot be read, our witness is not known to be
        # there. uninstall() is where an unreadable file must stop, not here.
        return False
