"""Hooks-directory wiring (Cline): one executable file per event, named exactly as the event."""

from __future__ import annotations

import os
import stat

from .install_atomic import write_text
from .install_config import BEGIN, END, ConfigUnreadableError, block_bounds, read_text, remove_block, render_block

#: Cline runs a hook file through its shebang line and requires one (.clinerules/hooks/README.md).
SHEBANG = "#!/bin/sh"

_EXECUTABLE = stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH


def block(command, owner):
    """Our marked block: the command line, run on the hook's own stdin."""
    return "%s %s\n%s\n%s %s" % (BEGIN, owner, command, END, owner)


def script(command, owner):
    """A whole hook file as install writes it new."""
    return "%s\n%s\n" % (SHEBANG, block(command, owner))


def _text(path):
    try:
        return read_text(path)
    except (OSError, ConfigUnreadableError):
        return None


def _refuse_link(path):
    """A planted symlink would have install write through it to its target, and chmod that +x."""
    if os.path.islink(path):
        raise ConfigUnreadableError("%s is a symlink; refusing to write or remove through it." % path)


def _owned(path, owner):
    text = _text(path) if os.path.isfile(path) else None
    return text is not None and block_bounds(text, owner) is not None


def write(directory, fragment, owner):
    """Write one executable per event; a file of the same name that is not ours refuses them all."""
    for name in fragment:
        path = os.path.join(directory, name)
        _refuse_link(path)
        if os.path.lexists(path) and not _owned(path, owner):
            raise ConfigUnreadableError(
                "%s exists and carries no %s block; refusing to overwrite it (Cline runs one %s per hooks "
                "directory)." % (path, owner, name)
            )
    prepared = []
    for name, command in fragment.items():
        path = os.path.join(directory, name)
        text = render_block(path, command + "\n", owner) if os.path.exists(path) else script(command, owner)
        prepared.append((path, text))
    for path, text in prepared:
        write_text(path, text, mode=0o600)
        os.chmod(path, os.stat(path).st_mode | _EXECUTABLE)


def remove(directory, names, owner):
    """Remove our block from each named file, and the file itself when nothing else is left."""
    changed = False
    for name in names:
        path = os.path.join(directory, name)
        _refuse_link(path)
        if not _owned(path, owner):
            continue
        remove_block(path, owner)
        if _text(path).strip() in ("", SHEBANG):
            os.remove(path)
        changed = True
    return changed


def installed(directory, names, owner, fragment=None):
    """Any named file carries our block; with `fragment`, every file it names carries exactly that block."""
    if fragment is None:
        return any(_owned(os.path.join(directory, name), owner) for name in names)
    for name, command in fragment.items():
        text = _text(os.path.join(directory, name)) or ""
        bounds = block_bounds(text, owner)
        if bounds is None or text[bounds[0] : bounds[1]] != block(command, owner):
            return False
    return bool(fragment)
