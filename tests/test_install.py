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
    """Codex CLI < 0.143.0 rejects its whole hooks file over one unexpected top-level key
    (openai/codex#30397: "unknown field `_agentseam`, expected `description` or `hooks`",
    witnessed live installing here 2026-08-27) -- silently dropping every hook, not just
    ours. The marker must only ever land on a list item (a leaf command entry, or a
    matcher/hooks group wrapping one), never on the container object every adapter's
    hook_config() returns.
    """
    for agent in sorted(adapters.ADAPTERS):
        if getattr(adapters.get(agent), "CONFIG_FORMAT", "json") == "toml":
            continue  # TOML configs use the marker-delimited block instead, not this path
        path = Path(I.install(agent, ["pre_tool"], "handler", str(tmp_path / agent)))
        body = json.loads(path.read_text())
        assert I.MARKER not in body, agent


def test_codex_cli_install_round_trips_without_a_top_level_marker(tmp_path):
    root = str(tmp_path)
    path = Path(I.install("codex_cli", ["pre_tool"], "guard.py", repo_root=root))
    body = json.loads(path.read_text())
    assert I.MARKER not in body
    entry = body["hooks"]["preToolUse"][0]
    assert entry["hooks"][0]["command"] == "guard.py"
    assert I.installed("codex_cli", root)

    assert I.uninstall("codex_cli", root) is True
    assert I.installed("codex_cli", root) is False


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


def test_a_user_scoped_config_path_is_not_nested_under_the_repo(tmp_path, monkeypatch):
    """`~/...` means the user's home, not a directory literally named `~` in the repo.

    `_resolve` joined every CONFIG_PATH onto repo_root, so Junie's user-scoped path became
    `./~/.junie/config.json` -- a real file, written where no agent will ever read it. At
    capture time that is indistinguishable from a vendor whose hooks do not fire, which is
    the worst way to be wrong: it reads as evidence against the vendor.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    written = I.install("junie", ["pre_tool"], "guard.py", str(tmp_path))

    assert not (tmp_path / "~").exists(), "created a directory literally named ~"
    assert Path(written) == tmp_path / ".junie" / "config.json"
    assert I.installed("junie", str(tmp_path))


def test_install_never_destroys_a_config_it_cannot_parse(tmp_path, monkeypatch):
    """The data-loss bug: _load returned {} on any parse failure, so install merged its
    fragment into an empty object and wrote that back -- wiping the user's whole config.

    For Junie, config.json IS the CLI configuration, so a stray byte cost everything. A
    UTF-8 BOM (Windows editors add one) is the common trigger and is not corruption, so it
    must be tolerated; genuine corruption must stop install, never overwrite.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".junie" / "config.json"
    cfg.parent.mkdir()

    # A BOM-prefixed real config: tolerated, preserved, and wired.
    cfg.write_bytes(b"\xef\xbb\xbf" + json.dumps({"theme": "dark", "customModel": "keep-me"}).encode())
    I.install("junie", ["pre_tool"], "guard.py")
    after = json.loads(cfg.read_text())
    assert after["customModel"] == "keep-me" and after["theme"] == "dark", "user settings were destroyed"
    assert "hooks" in after, "the hook was not wired"

    # Genuine corruption: install refuses rather than clobbering.
    cfg.write_text("{ this is not json ,,, }")
    with pytest.raises(I.ConfigUnreadable):
        I.install("junie", ["pre_tool"], "guard.py")
    assert cfg.read_text() == "{ this is not json ,,, }", "a config we could not parse was overwritten"

    # An undecodable encoding (UTF-16) is unreadable, not corruption-in-JSON, but must take
    # the same preserve-and-report path rather than crashing with a raw UnicodeDecodeError.
    cfg.write_bytes(json.dumps({"keep": "me"}).encode("utf-16"))
    with pytest.raises(I.ConfigUnreadable):
        I.install("junie", ["pre_tool"], "guard.py")
    assert cfg.read_bytes()[:2] == b"\xff\xfe", "a UTF-16 config was overwritten"


def test_a_query_never_raises_on_an_unparseable_config(tmp_path, monkeypatch):
    """installed() is a read-only question; a corrupt file means "not known to be there",
    not a crash. uninstall() is where an unreadable file must stop instead."""
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".junie" / "config.json"
    cfg.parent.mkdir()
    cfg.write_text("{ broken ,,, }")

    assert I.installed("junie") is False
    with pytest.raises(I.ConfigUnreadable):
        I.uninstall("junie")
    assert cfg.read_text() == "{ broken ,,, }", "uninstall must not rewrite a file it cannot parse"


def test_a_query_never_raises_on_an_undecodable_toml_config(tmp_path, monkeypatch):
    """The TOML branch of installed() must uphold the same "never raises" contract as the
    JSON branch: a config that exists but is not UTF-8 (a UTF-16 file, a stray byte) means
    "not known to be there", not a crash. It read the file with no guard before."""
    monkeypatch.setenv("HOME", str(tmp_path))
    cfg = tmp_path / ".kimi-code" / "config.toml"
    cfg.parent.mkdir()
    cfg.write_bytes('event = "x"'.encode("utf-16"))

    assert I.installed("kimi_code") is False
    assert cfg.read_bytes()[:2] == b"\xff\xfe", "a read-only query must not touch the file"
