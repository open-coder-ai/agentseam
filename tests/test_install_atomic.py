"""Installs never half-apply: atomic writes, a lock around the json read-modify-write, legacy cleaned last."""

from __future__ import annotations

import json
import os
import threading

import pytest

from agentseam import install as I
from agentseam import install_atomic, instructions

_LEGACY = ".windsurf/hooks.json"
_CURRENT = ".devin/hooks.json"
_RACERS = 20


def _write(root, rel, data):
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")


def _failing_replace(monkeypatch):
    def boom(src, dst):  # noqa: ARG001
        raise OSError("disk full")

    monkeypatch.setattr(install_atomic.os, "replace", boom)


def _race(root, owners):
    barrier = threading.Barrier(len(owners))
    errors = []

    def go(owner):
        try:
            barrier.wait()
            I.install("claude_code", ["pre_tool"], "guard-" + owner, str(root), owner=owner)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=go, args=(o,)) for o in owners]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    with open(I.config_path("claude_code", str(root)), encoding="utf-8") as fh:
        return json.load(fh)


@pytest.mark.parametrize("round_", range(_RACERS))
def test_two_owners_installing_at_once_keep_both(tmp_path, round_):
    data = _race(tmp_path, ["one", "two"])
    owners = {e["_agentseam"] for entries in data["hooks"].values() for e in entries}
    assert owners == {"one", "two"}, round_


def test_failed_replace_keeps_the_old_file_and_leaves_no_temp(tmp_path, monkeypatch):
    path = tmp_path / "c.json"
    path.write_text('{"a": 1}', encoding="utf-8")
    _failing_replace(monkeypatch)
    with pytest.raises(OSError, match="disk full"):
        install_atomic.write_text(str(path), "{}")
    assert path.read_text(encoding="utf-8") == '{"a": 1}'
    assert [n for n in os.listdir(tmp_path) if n.endswith(".tmp")] == []


def test_failed_target_write_leaves_the_legacy_hook_intact(tmp_path, monkeypatch):
    legacy = {"hooks": {"pre_run_command": [{"command": "old", "_agentseam": "agentseam"}]}}
    _write(tmp_path, _LEGACY, legacy)
    _failing_replace(monkeypatch)
    with pytest.raises(OSError, match="disk full"):
        I.install("windsurf", ["pre_tool"], "g", str(tmp_path))
    assert json.loads((tmp_path / _LEGACY).read_text(encoding="utf-8")) == legacy
    assert not (tmp_path / _CURRENT).exists()


def test_write_keeps_mode_and_goes_through_a_symlink(tmp_path):
    real = tmp_path / "real.json"
    real.write_text("{}", encoding="utf-8")
    real.chmod(0o640)
    link = tmp_path / "link.json"
    link.symlink_to(real)
    install_atomic.write_text(str(link), '{"x": 1}')
    assert link.is_symlink()
    assert real.read_text(encoding="utf-8") == '{"x": 1}'
    assert real.stat().st_mode & 0o777 == 0o640


def test_instruction_write_is_atomic(tmp_path, monkeypatch):
    (tmp_path / "AGENTS.md").write_text("mine\n", encoding="utf-8")
    _failing_replace(monkeypatch)
    with pytest.raises(OSError, match="disk full"):
        instructions.write("rules", ["codex_cli"], str(tmp_path))
    assert (tmp_path / "AGENTS.md").read_text(encoding="utf-8") == "mine\n"


def test_cline_hook_files_are_written_by_replace(tmp_path):
    I.install("cline", ["pre_tool"], "g", str(tmp_path))
    hooks = tmp_path / ".clinerules" / "hooks"
    assert [p.name for p in hooks.iterdir()] == ["PreToolUse"]
    assert os.access(hooks / "PreToolUse", os.X_OK)


@pytest.mark.parametrize("round_", range(_RACERS))
def test_two_owners_installing_a_toml_block_at_once_keep_both(tmp_path, round_):
    owners = ["one", "two"]
    barrier = threading.Barrier(len(owners))
    errors = []

    def go(owner):
        try:
            barrier.wait()
            I.install("mistral_vibe", ["pre_tool"], "guard-" + owner, str(tmp_path), owner=owner)
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=go, args=(o,)) for o in owners]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    text = (tmp_path / ".vibe" / "hooks.toml").read_text(encoding="utf-8")
    assert "guard-one" in text
    assert "guard-two" in text, round_


def test_cline_never_writes_through_a_link_planted_after_the_check(tmp_path, monkeypatch):
    victim = tmp_path / "victim.txt"
    victim.write_text("keep\n", encoding="utf-8")
    hooks = tmp_path / ".clinerules" / "hooks"
    real_link = os.link

    def plant_then_link(src, dst):
        os.symlink(victim, dst)
        real_link(src, dst)

    monkeypatch.setattr(install_atomic.os, "link", plant_then_link)
    with pytest.raises(FileExistsError):
        I.install("cline", ["pre_tool"], "g", str(tmp_path))
    assert victim.read_text(encoding="utf-8") == "keep\n"
    assert os.path.islink(hooks / "PreToolUse")
    assert [n for n in os.listdir(hooks) if n.endswith(".tmp")] == []


def test_a_new_file_is_private_and_an_existing_one_keeps_its_mode(tmp_path):
    fresh = tmp_path / "fresh.json"
    install_atomic.write_text(str(fresh), "{}")
    assert fresh.stat().st_mode & 0o777 == 0o600
    old = tmp_path / "old.json"
    old.write_text("{}", encoding="utf-8")
    old.chmod(0o644)
    install_atomic.write_text(str(old), '{"a": 1}')
    assert old.stat().st_mode & 0o777 == 0o644


def test_a_new_instruction_file_gets_the_umask_default_and_an_existing_one_keeps_its_mode(tmp_path):
    mask = os.umask(0o022)
    try:
        instructions.write("rules", ["codex_cli"], str(tmp_path))
        assert (tmp_path / "AGENTS.md").stat().st_mode & 0o777 == 0o666 & ~0o022
        (tmp_path / "AGENTS.md").chmod(0o640)
        instructions.write("other rules", ["codex_cli"], str(tmp_path))
        assert (tmp_path / "AGENTS.md").stat().st_mode & 0o777 == 0o640
    finally:
        os.umask(mask)
