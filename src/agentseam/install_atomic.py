"""Crash-safe config writes: temp file then `os.replace`, and an advisory lock for read-modify-write."""

from __future__ import annotations

import contextlib
import os
import tempfile
import time

try:
    import fcntl
except ImportError:
    fcntl = None
try:
    import msvcrt
except ImportError:
    msvcrt = None

_DEFAULT_MODE = 0o600
_LOCK_WAIT_SECONDS = 30


def umask_mode():
    """The mode a plain open() gives a new file under the process umask."""
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


def write_bytes(path, data, mode=None):
    """Replace `path` with `data` in one step; a failure leaves the old file and no temp file behind.

    A symlinked `path` is written through (its target is replaced, the link stays). The file keeps
    its own permission bits; a new one gets `mode`, default 0o600 (a config carrying hook commands
    has no reader but its owner).
    """
    target = os.path.realpath(path)
    parent = os.path.dirname(target) or "."
    os.makedirs(parent, exist_ok=True)
    try:
        mode = os.stat(target).st_mode & 0o7777
    except OSError:
        mode = _DEFAULT_MODE if mode is None else mode
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".agentseam-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.replace(tmp, target)
    except BaseException:
        with contextlib.suppress(OSError):
            os.remove(tmp)
        raise


def write_text(path, text, mode=None):
    """`write_bytes` of `text` encoded as UTF-8. Encoding comes first, so a bad text touches nothing."""
    write_bytes(path, text.encode("utf-8"), mode)


def create_exclusive(path, text, mode=_DEFAULT_MODE):
    """Create `path` holding `text`, failing with FileExistsError if anything (a link included) is there.

    The content lands in a temp file first and is hard-linked into place, so `path` never appears
    half-written and is never opened through a link planted after the caller's check.
    """
    parent = os.path.dirname(path) or "."
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix=".agentseam-", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(text.encode("utf-8"))
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, mode)
        os.link(tmp, path)
    finally:
        with contextlib.suppress(OSError):
            os.remove(tmp)


def _lock(fh):
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        return
    deadline = time.monotonic() + _LOCK_WAIT_SECONDS
    while True:
        try:
            msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            if time.monotonic() > deadline:
                raise
            time.sleep(0.05)
        else:
            return


def _unlock(fh):
    if fcntl is not None:
        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    else:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)


@contextlib.contextmanager
def locked(path):
    """Hold an exclusive advisory lock on `<path>.lock` for a read-modify-write of `path`.

    Uses `fcntl` where present and `msvcrt` on Windows; a platform with neither gets no lock,
    only the atomic write, so two racing installs there can still lose one owner's entries.
    """
    if fcntl is None and msvcrt is None:
        yield
        return
    target = os.path.realpath(path)
    os.makedirs(os.path.dirname(target) or ".", exist_ok=True)
    with open(target + ".lock", "a+b") as fh:
        if msvcrt is not None and fcntl is None:
            fh.write(b"\0")
            fh.flush()
            fh.seek(0)
        _lock(fh)
        try:
            yield
        finally:
            _unlock(fh)
