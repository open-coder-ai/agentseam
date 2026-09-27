"""install() edits a user's file: matcher where it means something, no debris, no clobbering."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentseam import install as I  # noqa: E402

_SETTINGS = ".claude/settings.json"


def _read(tmp_path):
    return json.loads((tmp_path / _SETTINGS).read_text(encoding="utf-8"))


def _write(tmp_path, data):
    path = tmp_path / _SETTINGS
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def test_a_tool_matcher_is_written_only_at_tool_events(tmp_path):
    """Claude Code's SessionStart matcher is the session source, so a `Bash` there never fires."""
    I.install("claude_code", ["pre_tool", "post_tool", "stop", "session_start"], "g", str(tmp_path), matcher="Bash")
    hooks = _read(tmp_path)["hooks"]
    assert hooks["PreToolUse"][0]["matcher"] == "Bash"
    assert hooks["PostToolUse"][0]["matcher"] == "Bash"
    assert "matcher" not in hooks["Stop"][0]
    assert "matcher" not in hooks["SessionStart"][0]


def test_uninstall_prunes_the_event_lists_it_emptied_and_keeps_the_users_own(tmp_path):
    _write(tmp_path, {"hooks": {"Notification": []}, "model": "opus"})
    I.install("claude_code", ["pre_tool", "stop"], "g", str(tmp_path))
    assert I.uninstall("claude_code", str(tmp_path))
    assert _read(tmp_path) == {"hooks": {"Notification": []}, "model": "opus"}


def test_uninstall_of_a_file_it_alone_filled_leaves_no_empty_scaffolding(tmp_path):
    I.install("claude_code", ["pre_tool"], "g", str(tmp_path))
    I.uninstall("claude_code", str(tmp_path))
    assert _read(tmp_path) == {}


def test_reinstalling_fewer_events_drops_the_event_it_no_longer_wires(tmp_path):
    I.install("claude_code", ["pre_tool", "stop"], "g", str(tmp_path))
    I.install("claude_code", ["pre_tool"], "g", str(tmp_path))
    assert list(_read(tmp_path)["hooks"]) == ["PreToolUse"]


def test_an_event_value_that_is_not_a_list_is_refused_not_overwritten(tmp_path):
    _write(tmp_path, {"hooks": {"PreToolUse": {"matcher": "Bash", "command": "mine"}}})
    before = (tmp_path / _SETTINGS).read_text(encoding="utf-8")
    with pytest.raises(I.ConfigUnreadableError, match="hooks.PreToolUse"):
        I.install("claude_code", ["pre_tool"], "g", str(tmp_path))
    assert (tmp_path / _SETTINGS).read_text(encoding="utf-8") == before


def test_the_users_key_order_survives_an_install(tmp_path):
    _write(tmp_path, {"permissions": {"deny": []}, "hooks": {"Stop": []}, "env": {"Z": "1", "A": "2"}})
    I.install("claude_code", ["pre_tool"], "g", str(tmp_path))
    data = _read(tmp_path)
    assert list(data) == ["permissions", "hooks", "env"]
    assert list(data["env"]) == ["Z", "A"]
    assert list(data["hooks"]) == ["Stop", "PreToolUse"]
