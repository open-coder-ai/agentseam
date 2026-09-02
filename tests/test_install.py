"""Wiring must be idempotent, surgical, and never clobber a user's own hooks."""

import json
import sys
from pathlib import Path

import pytest

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


def test_the_marker_never_lands_on_a_top_level_container(tmp_path):
    """Codex CLI < 0.143.0 rejects its whole hooks file over one unexpected top-level key"""
    for agent in sorted(adapters.ADAPTERS):
        if getattr(adapters.get(agent), "CONFIG_FORMAT", "json") == "toml":
            continue
        path = Path(I.install(agent, ["pre_tool"], "handler", str(tmp_path / agent)))
        body = json.loads(path.read_text())
        assert I.MARKER not in body, agent


def test_codex_cli_install_round_trips_without_a_top_level_marker(tmp_path):
    root = str(tmp_path)
    path = Path(I.install("codex_cli", ["pre_tool"], "guard.py", repo_root=root))
    body = json.loads(path.read_text())
    assert I.MARKER not in body
    entry = body["hooks"]["PreToolUse"][0]
    assert entry["hooks"][0]["command"] == "guard.py"
    assert I.installed("codex_cli", root)

    assert I.uninstall("codex_cli", root) is True
    assert I.installed("codex_cli", root) is False


def test_devin_install_round_trips_in_its_wrapperless_file(tmp_path):
    """`.devin/hooks.v1.json` holds the hooks object as the whole file, with no wrapper key."""
    root = str(tmp_path)
    path = Path(I.install("devin", ["pre_tool"], "guard.py", repo_root=root))
    assert path.name == "hooks.v1.json"
    body = json.loads(path.read_text())
    assert "PreToolUse" in body and "hooks" not in body
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


def test_a_user_scoped_config_path_is_not_nested_under_the_repo(tmp_path, monkeypatch):
    """`~/...` means the user's home, not a directory literally named `~` in the repo."""
    monkeypatch.setenv("HOME", str(tmp_path))
    written = I.install("junie", ["pre_tool"], "guard.py", str(tmp_path))

    assert not (tmp_path / "~").exists(), "created a directory literally named ~"
    assert Path(written) == tmp_path / ".junie" / "config.json"
    assert I.installed("junie", str(tmp_path))


def test_install_never_destroys_a_config_it_cannot_parse(tmp_path, monkeypatch):
    """The data-loss bug: _load returned {} on any parse failure, so install merged its"""
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".junie" / "config.json"
    cfg.parent.mkdir()

    cfg.write_bytes(b"\xef\xbb\xbf" + json.dumps({"theme": "dark", "customModel": "keep-me"}).encode())
    I.install("junie", ["pre_tool"], "guard.py")
    after = json.loads(cfg.read_text())
    assert after["customModel"] == "keep-me" and after["theme"] == "dark", "user settings were destroyed"
    assert "hooks" in after, "the hook was not wired"

    cfg.write_text("{ this is not json ,,, }")
    with pytest.raises(I.ConfigUnreadableError):
        I.install("junie", ["pre_tool"], "guard.py")
    assert cfg.read_text() == "{ this is not json ,,, }", "a config we could not parse was overwritten"

    cfg.write_bytes(json.dumps({"keep": "me"}).encode("utf-16"))
    with pytest.raises(I.ConfigUnreadableError):
        I.install("junie", ["pre_tool"], "guard.py")
    assert cfg.read_bytes()[:2] == b"\xff\xfe", "a UTF-16 config was overwritten"


def test_a_query_never_raises_on_an_unparseable_config(tmp_path, monkeypatch):
    """installed() is a read-only question; a corrupt file means "not known to be there","""
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".junie" / "config.json"
    cfg.parent.mkdir()
    cfg.write_text("{ broken ,,, }")

    assert I.installed("junie") is False
    with pytest.raises(I.ConfigUnreadableError):
        I.uninstall("junie")
    assert cfg.read_text() == "{ broken ,,, }", "uninstall must not rewrite a file it cannot parse"


def test_a_query_never_raises_on_an_undecodable_toml_config(tmp_path, monkeypatch):
    """The TOML branch of installed() must uphold the same "never raises" contract as the"""
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".kimi-code" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_bytes('event = "x"'.encode("utf-16"))

    assert I.installed("kimi_code") is False
    assert cfg.read_bytes()[:2] == b"\xff\xfe", "a read-only query must not touch the file"


def test_uninstalling_one_owner_leaves_another_owners_mark_intact(tmp_path):
    """Ownership is the only thing that makes uninstall surgical, so erasing someone else's"""
    from agentseam import install as install_mod

    install_mod.install("cursor", ["pre_tool"], "guard-A", repo_root=str(tmp_path), owner="team-a")
    install_mod.install("cursor", ["pre_tool"], "guard-B", repo_root=str(tmp_path), owner="team-b")
    assert install_mod.installed("cursor", repo_root=str(tmp_path), owner="team-a")
    assert install_mod.installed("cursor", repo_root=str(tmp_path), owner="team-b"), (
        "the second install erased the first"
    )

    install_mod.uninstall("cursor", repo_root=str(tmp_path), owner="team-a")
    entries = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())["hooks"]["preToolUse"]
    assert [e["command"] for e in entries] == ["guard-B"], entries
    assert install_mod.installed("cursor", repo_root=str(tmp_path), owner="team-b")


def test_an_observer_is_not_wired_as_a_fail_closed_gate(tmp_path):
    """The capture probe always allows. Wired as a gate on Cursor it inherits"""
    from agentseam import install as install_mod

    install_mod.install("cursor", ["pre_tool"], "probe", repo_root=str(tmp_path), fail_closed=False)
    entry = json.loads((tmp_path / ".cursor" / "hooks.json").read_text())["hooks"]["preToolUse"][0]
    assert "failClosed" not in entry, entry

    guard = tmp_path / "guard"
    install_mod.install("cursor", ["pre_tool"], "real-guard", repo_root=str(guard))
    assert json.loads((guard / ".cursor" / "hooks.json").read_text())["hooks"]["preToolUse"][0]["failClosed"] is True


def test_the_witness_asks_about_ownership_not_about_a_substring(tmp_path):
    """`installed()` used to be `owner in json.dumps(config)` -- a substring test over the"""
    from agentseam import install as install_mod

    install_mod.install("antigravity", ["pre_tool"], "g", repo_root=str(tmp_path))
    assert install_mod.installed("antigravity", repo_root=str(tmp_path))
    install_mod.uninstall("antigravity", repo_root=str(tmp_path))
    assert not install_mod.installed("antigravity", repo_root=str(tmp_path)), "an empty group is not a guard"

    other = tmp_path / "other"
    install_mod.install("cursor", ["pre_tool"], "g", repo_root=str(other), owner="agentseam-capture")
    assert install_mod.installed("cursor", repo_root=str(other), owner="agentseam-capture")
    assert not install_mod.installed("cursor", repo_root=str(other)), "a prefix of the owner is not the owner"
