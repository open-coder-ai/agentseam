"""claude_code FileChanged watches only the files its matcher names; install never claims it without them."""

from __future__ import annotations

import json
import warnings

import pytest

import agentseam as A
from agentseam import cli
from agentseam import install as I


def _hooks(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)["hooks"]


def test_file_changed_is_not_wired_without_a_watch_list(tmp_path):
    """code.claude.com/docs/en/hooks (FileChanged, read 2026-10-13): "Claude Code starts the watcher
    only when something names a file to watch". A matcher-less FileChanged entry can never fire."""
    with pytest.warns(UserWarning, match="file_changed not wired for claude_code"):
        path = I.install("claude_code", [A.PRE_TOOL, A.FILE_CHANGED], "guard", str(tmp_path))
    assert set(_hooks(path)) == {"PreToolUse"}


def test_file_changed_alone_without_a_watch_list_is_refused(tmp_path):
    with pytest.raises(ValueError, match="watch="):
        I.install("claude_code", [A.FILE_CHANGED], "guard", str(tmp_path))
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_the_watch_list_is_the_file_changed_matcher(tmp_path):
    """Each '|' segment is "registered as a literal filename in the working directory"."""
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        path = I.install(
            "claude_code",
            [A.PRE_TOOL, A.FILE_CHANGED],
            "guard",
            str(tmp_path),
            matcher="Bash",
            watch=[".envrc", ".env"],
        )
    hooks = _hooks(path)
    assert [entry["matcher"] for entry in hooks["FileChanged"]] == [".envrc|.env"]
    assert [entry["matcher"] for entry in hooks["PreToolUse"]] == ["Bash"]
    assert I.installed("claude_code", str(tmp_path), events=[A.FILE_CHANGED], command="guard", watch=[".envrc", ".env"])
    assert not I.installed("claude_code", str(tmp_path), events=[A.FILE_CHANGED], command="guard", watch=[".env"])


def test_a_watch_item_carrying_the_separator_is_refused(tmp_path):
    with pytest.raises(ValueError, match="without '\\|'"):
        I.install("claude_code", [A.FILE_CHANGED], "guard", str(tmp_path), watch=[".envrc|.env"])


def test_the_cli_says_why_once_and_does_not_list_the_event_as_wired(tmp_path, capsys):
    code = cli.main(
        ["install", "claude_code", "guard", "--events", "pre_tool", "file_changed", "--repo", str(tmp_path)]
    )
    out = capsys.readouterr()
    assert code == 0
    assert out.out.count("file_changed not wired for claude_code") == 1
    assert "file_changed=" not in out.out
    assert "file_changed" not in out.err


def test_the_cli_wires_file_changed_given_watch(tmp_path, capsys):
    argv = ["install", "claude_code", "guard", "--events", "file_changed", "--watch", ".envrc", "--repo", str(tmp_path)]
    assert cli.main(argv) == 0
    assert "file_changed=" in capsys.readouterr().out
    assert _hooks(tmp_path / ".claude" / "settings.json")["FileChanged"][0]["matcher"] == ".envrc"
