"""Wiring must be idempotent, surgical, and never clobber a user's own hooks."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentseam import adapters
from agentseam import install as I


def test_install_creates_config(tmp_path):
    path = I.install("claude_code", ["pre_tool"], "python3 h.py", str(tmp_path), matcher="Write|Edit")
    data = json.loads(Path(path).read_text())
    entry = data["hooks"]["PreToolUse"][0]
    assert entry["matcher"] == "Write|Edit"
    assert entry["hooks"][0]["command"] == "python3 h.py"
    assert I.installed("claude_code", str(tmp_path))


def test_install_is_idempotent(tmp_path):
    for _ in range(3):
        path = I.install("claude_code", ["pre_tool"], "python3 h.py", str(tmp_path))
    data = json.loads(Path(path).read_text())
    assert len(data["hooks"]["PreToolUse"]) == 1, "re-install duplicated our entry"


def test_uninstall_leaves_user_hooks_intact(tmp_path):
    cfg = tmp_path / ".claude" / "settings.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        json.dumps(
            {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "user-own.sh"}]}]}}
        )
    )

    I.install("claude_code", ["pre_tool"], "python3 h.py", str(tmp_path))
    assert len(json.loads(cfg.read_text())["hooks"]["PreToolUse"]) == 2

    assert I.uninstall("claude_code", str(tmp_path)) is True
    remaining = json.loads(cfg.read_text())["hooks"]["PreToolUse"]
    assert len(remaining) == 1
    assert remaining[0]["hooks"][0]["command"] == "user-own.sh"
    assert not I.installed("claude_code", str(tmp_path))


def test_uninstall_when_absent_is_noop(tmp_path):
    assert I.uninstall("claude_code", str(tmp_path)) is False


def test_every_agent_with_a_surface_can_be_wired(tmp_path):
    for agent in sorted(adapters.ADAPTERS):
        path = I.install(agent, ["pre_tool"], "handler", str(tmp_path / agent))
        assert Path(path).exists(), agent
        assert I.installed(agent, str(tmp_path / agent)), agent


def test_devin_install_round_trips_in_its_wrapperless_file(tmp_path):
    """`.devin/hooks.v1.json` holds the hooks object as the whole file, with no wrapper key.

    The installer is format-agnostic by design, so this is the test that proves it rather
    than a special case in the code.
    """
    root = str(tmp_path)
    path = Path(I.install("devin", ["pre_tool"], "guard.py", repo_root=root))
    assert path.name == "hooks.v1.json"
    body = json.loads(path.read_text())
    assert "PreToolUse" in body and "hooks" not in body  # the object IS the file
    assert I.installed("devin", root)

    assert I.uninstall("devin", root) is True
    assert I.installed("devin", root) is False


def test_installing_devin_leaves_a_hand_written_hook_alone(tmp_path):
    """Devin also reads .claude/settings.json, so users are likely to have their own here."""
    root = Path(tmp_path)
    (root / ".devin").mkdir()
    own = {"PreToolUse": [{"hooks": [{"type": "command", "command": "mine.sh"}]}]}
    (root / ".devin" / "hooks.v1.json").write_text(json.dumps(own))

    I.install("devin", ["pre_tool"], "guard.py", repo_root=str(root))
    I.uninstall("devin", str(root))

    after = json.loads((root / ".devin" / "hooks.v1.json").read_text())
    assert after == own


def test_cursor_install_writes_the_generic_gate_with_fail_closed(tmp_path):
    root = str(tmp_path)
    path = Path(I.install("cursor", ["pre_tool"], "guard.py", repo_root=root))
    body = json.loads(path.read_text())
    entry = body["hooks"]["preToolUse"][0]
    assert entry["command"] == "guard.py"
    assert entry["failClosed"] is True
    assert I.uninstall("cursor", root) is True
