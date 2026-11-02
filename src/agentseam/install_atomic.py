"""Crash-safe config writes: temp file then `os.replace`, and an advisory lock for read-modify-write."""

from __future__ import annotations

import contextlib
import getpass
import hashlib
import os
import stat
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
_LOCK_DIR_MODE = 0o700


def umask_mode():
    """The mode a plain open() gives a new file under the process umask."""
    mask = os.umask(0)
    os.umask(mask)
    return 0o666 & ~mask


class PathEscapesRepoError(ValueError):
    """A repo-relative path resolves outside the repo, or through a link that points nowhere."""


def refuse_escape(path, repo_root):
    """Raise PathEscapesRepoError unless `path` stays inside `repo_root` once every link is followed.

    A link that resolves inside the repo is fine (CLAUDE.md -> AGENTS.md); one that leaves it, or
    dangles so that writing would create its target, is a path the repo's contents chose.
    """
    if os.path.islink(path) and not os.path.exists(path):
        raise PathEscapesRepoError("%s is a dangling symlink; refusing to create its target." % path)
    root = os.path.realpath(repo_root)
    if os.path.commonpath([root, os.path.realpath(path)]) != root:
        raise PathEscapesRepoError(
            "%s resolves outside %s through a symlink; refusing to write through it." % (path, repo_root)
        )


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


class LockDirectoryError(OSError):
    """The per-user lock directory is a link or belongs to someone else; locking there is refused."""


def _owner_tag():
    getuid = getattr(os, "getuid", None)
    return str(getuid()) if getuid else getpass.getuser()


def _lock_dir_candidates():
    if os.name == "nt":
        base = os.environ.get("LOCALAPPDATA")
    else:
        base = os.environ.get("XDG_CACHE_HOME")
        if not base or not os.path.isabs(base):
            base = os.path.join(os.path.expanduser("~"), ".cache")
    candidates = [os.path.join(base, "agentseam", "locks")] if base else []
    candidates.append(os.path.join(tempfile.gettempdir(), "agentseam-locks-" + _owner_tag()))
    return candidates


def _checked_dir(path):
    try:
        os.makedirs(path, mode=_LOCK_DIR_MODE, exist_ok=True)
    except PermissionError:
        if not os.path.isdir(path):
            raise
    if not hasattr(os, "getuid"):
        return path
    info = os.lstat(path)
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise LockDirectoryError("%s is a link or not a directory; refusing to lock there." % path)
    if info.st_uid != os.getuid():
        raise LockDirectoryError("%s is not owned by this user; refusing to lock there." % path)
    if info.st_mode & 0o077:
        os.chmod(path, _LOCK_DIR_MODE)
    return path


def lock_path(path):
    """The lock file for `path`: the sha256 of its realpath inside a per-user directory outside any repo."""
    digest = hashlib.sha256(os.path.realpath(path).encode("utf-8", "surrogatepass")).hexdigest()
    failure = None
    for directory in _lock_dir_candidates():
        try:
            return os.path.join(_checked_dir(directory), digest + ".lock")
        except LockDirectoryError:
            raise
        except OSError as exc:
            failure = exc
    raise failure


def _open_lock(path):
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    return os.fdopen(os.open(lock_path(path), flags, _DEFAULT_MODE), "r+b")


@contextlib.contextmanager
def locked(path):
    """Hold an exclusive advisory lock, kept in a per-user directory, for a read-modify-write of `path`.

    Uses `fcntl` where present and `msvcrt` on Windows; a platform with neither gets no lock,
    only the atomic write, so two racing installs there can still lose one owner's entries.
    The lock file never sits beside the config, so an install leaves nothing untracked in a repo.
    """
    if fcntl is None and msvcrt is None:
        yield
        return
    with _open_lock(path) as fh:
        _lock(fh)
        try:
            yield
        finally:
            _unlock(fh)
