"""Install locks live in a per-user directory, so an install leaves nothing beside a repo's configs."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess

import pytest

from agentseam import install as I
from agentseam import install_atomic

_POSIX = hasattr(os, "getuid")


@pytest.fixture
def cache(tmp_path, monkeypatch):
    base = tmp_path / "cache"
    monkeypatch.setenv("LOCALAPPDATA" if os.name == "nt" else "XDG_CACHE_HOME", str(base))
    return base / "agentseam" / "locks"


def test_lock_file_is_named_by_the_sha256_of_the_realpath(tmp_path, cache):
    config = tmp_path / "repo" / ".claude" / "settings.json"
    digest = hashlib.sha256(os.path.realpath(config).encode("utf-8")).hexdigest()
    assert install_atomic.lock_path(str(config)) == str(cache / (digest + ".lock"))


@pytest.mark.skipif(not _POSIX, reason="mode bits are POSIX")
def test_lock_directory_is_private(tmp_path, cache):
    install_atomic.lock_path(str(tmp_path / "x.json"))
    assert cache.stat().st_mode & 0o777 == 0o700


def test_an_install_leaves_no_file_beside_the_config(tmp_path, cache):
    repo = tmp_path / "repo"
    repo.mkdir()
    I.install("claude_code", ["pre_tool"], "guard", str(repo))
    I.install("claude_code", ["pre_tool"], "guard-two", str(repo), owner="two")
    names = sorted(p.name for p in (repo / ".claude").iterdir())
    assert names == ["settings.json"]
    assert len(list(cache.iterdir())) == 1


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_git_sees_nothing_untracked_after_an_install_into_a_committed_config(tmp_path, cache):
    repo = tmp_path / "repo"
    (repo / ".claude").mkdir(parents=True)
    (repo / ".claude" / "settings.json").write_text("{}\n", encoding="utf-8")
    run = ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.com"]
    subprocess.run([*run, "init", "-q"], check=True)
    subprocess.run([*run, "add", "."], check=True)
    subprocess.run([*run, "commit", "-q", "-m", "seed"], check=True)
    I.install("claude_code", ["pre_tool"], "guard", str(repo))
    subprocess.run([*run, "commit", "-qam", "installed"], check=True)
    out = subprocess.run([*run, "status", "--porcelain"], check=True, capture_output=True, text=True)
    assert out.stdout == ""


@pytest.mark.skipif(not _POSIX, reason="symlink and owner checks are POSIX")
def test_a_symlinked_lock_directory_is_refused(tmp_path, cache):
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    cache.parent.mkdir(parents=True)
    cache.symlink_to(elsewhere)
    with pytest.raises(install_atomic.LockDirectoryError), install_atomic.locked(str(tmp_path / "c.json")):
        pass
    assert list(elsewhere.iterdir()) == []


@pytest.mark.skipif(not _POSIX, reason="symlink and owner checks are POSIX")
def test_a_lock_directory_owned_by_someone_else_is_refused(tmp_path, cache, monkeypatch):
    cache.mkdir(parents=True)
    monkeypatch.setattr(install_atomic.os, "getuid", lambda: os.stat(cache).st_uid + 1)
    with pytest.raises(install_atomic.LockDirectoryError, match="not owned"):
        install_atomic.lock_path(str(tmp_path / "c.json"))


@pytest.mark.skipif(not _POSIX, reason="symlink and owner checks are POSIX")
def test_a_symlink_planted_at_the_lock_file_is_not_followed(tmp_path, cache):
    config = str(tmp_path / "c.json")
    victim = tmp_path / "victim"
    victim.write_text("keep", encoding="utf-8")
    cache.mkdir(parents=True)
    os.symlink(victim, install_atomic.lock_path(config))
    with pytest.raises(OSError), install_atomic.locked(config):
        pass
    assert victim.read_text(encoding="utf-8") == "keep"


def test_an_uncreatable_cache_falls_back_to_the_temp_directory(tmp_path, monkeypatch):
    blocker = tmp_path / "blocker"
    blocker.write_text("file", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA" if os.name == "nt" else "XDG_CACHE_HOME", str(blocker))
    monkeypatch.setattr(install_atomic.tempfile, "gettempdir", lambda: str(tmp_path / "tmp"))
    (tmp_path / "tmp").mkdir()
    got = install_atomic.lock_path(str(tmp_path / "c.json"))
    assert os.path.dirname(got).startswith(str(tmp_path / "tmp" / "agentseam-locks-"))
