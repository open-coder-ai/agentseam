"""Suite-wide fixtures."""

import os

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Every home variable `os.path.expanduser` consults, pointed at a per-test directory.

    junie and kimi_code keep their config under `~`, so an install test that forgets to move
    HOME edits the developer's real agent configuration. HOME alone is POSIX-shaped:
    `ntpath.expanduser` reads USERPROFILE, then HOMEDRIVE + HOMEPATH, never HOME.
    """
    home = tmp_path / "home"
    home.mkdir()
    drive, tail = os.path.splitdrive(str(home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("HOMEDRIVE", drive)
    monkeypatch.setenv("HOMEPATH", tail or str(home))
    return home
