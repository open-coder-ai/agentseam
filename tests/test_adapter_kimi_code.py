"""Kimi Code adapter: three blocking events out of twenty, and a TOML config."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import KM_NOTIFY, KM_POST, KM_SHELL, KM_WRITE  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402
from agentseam import install as I  # noqa: E402


def deny_all(_e):
    return Decision.deny("test-deny")


def test_client_type_is_the_only_thing_separating_it_from_claude_code():
    assert A.adapters.detect(KM_SHELL) == "kimi_code"
    stripped = {k: v for k, v in KM_SHELL.items() if k != "client_type"}
    assert A.adapters.detect(stripped) == "claude_code"


def test_pre_tool_use_blocks_with_the_reason_in_the_json_form():
    """Exit 2 blocks too, but only the JSON form carries the reason into the model's context."""
    text, code, event, _ = A.handle(KM_SHELL, deny_all)
    assert event.event == A.PRE_TOOL and event.command == "rm -rf /"
    body = json.loads(text)["hookSpecificOutput"]
    assert body == {"permissionDecision": "deny", "permissionDecisionReason": "test-deny"}
    assert code == 0


def test_a_write_payload_exposes_its_path_and_content():
    _, _, event, _ = A.handle(KM_WRITE, deny_all)
    assert event.path == "AGENTS.md" and "AWS_SECRET" in event.content


def test_observation_only_events_stay_silent():
    """Documented as fire-and-forget: a decision there would read as a gate that isn't one."""
    for payload in (KM_POST, KM_NOTIFY):
        text, code, _, _ = A.handle(payload, deny_all)
        assert (text, code) == ("", 0)


def test_a_degraded_rewrite_names_the_rewrite_not_a_confirmation():
    text, _, _, _ = A.handle(KM_SHELL, lambda e: Decision.rewrite({"command": "true"}, "redact it"))
    reason = json.loads(text)["hookSpecificOutput"]["permissionDecisionReason"]
    assert "redact it" in reason and "cannot modify" in reason


def test_only_three_events_are_recorded_as_blocking():
    mod = A.adapters.get("kimi_code")
    assert set(mod.BLOCKING_EVENTS) == {"PreToolUse", "UserPromptSubmit", "Stop"}


def test_render_config_emits_only_the_four_documented_fields():
    """A fifth field does not get ignored -- Kimi refuses to load the whole config file."""
    mod = A.adapters.get("kimi_code")
    rules = mod.hook_config([A.PRE_TOOL], "guard.py", matcher="Bash")
    toml = mod.render_config(rules)
    assert toml.startswith("[[hooks]]\n")
    assert 'event = "PreToolUse"' in toml and 'matcher = "Bash"' in toml
    keys = {line.split(" = ")[0] for line in toml.splitlines() if " = " in line}
    assert keys <= {"event", "matcher", "command", "timeout"}


def test_a_command_with_quotes_survives_the_toml_round_trip():
    mod = A.adapters.get("kimi_code")
    toml = mod.render_config([{"event": "PreToolUse", "command": 'sh -c "echo hi"'}])
    assert 'command = "sh -c \\"echo hi\\""' in toml


def test_install_appends_a_block_and_leaves_the_users_settings_untouched(tmp_path):
    """config.toml is the user's whole CLI configuration, not a hooks file."""
    root = Path(tmp_path)
    original = '[model]\nname = "kimi-k2"\n\n[[hooks]]\nevent = "Stop"\ncommand = "mine.sh"\n'
    (root / "config.toml").write_text(original)

    I.install("kimi_code", ["pre_tool"], "guard.py", str(root))
    after = (root / "config.toml").read_text()
    assert original.strip() in after
    assert "guard.py" in after and I.installed("kimi_code", str(root))

    assert I.uninstall("kimi_code", str(root)) is True
    assert (root / "config.toml").read_text().strip() == original.strip()
    assert I.installed("kimi_code", str(root)) is False


def test_reinstalling_replaces_our_block_rather_than_stacking_them(tmp_path):
    root = str(tmp_path)
    I.install("kimi_code", ["pre_tool"], "first.py", root)
    I.install("kimi_code", ["pre_tool"], "second.py", root)
    text = (Path(root) / "config.toml").read_text()
    assert text.count(I.BEGIN) == 1
    assert "second.py" in text and "first.py" not in text


def test_kimi_blocks_but_fails_open_and_the_notes_say_not_to_rely_on_it():
    assert A.can_block("kimi_code", A.PRE_TOOL)
    assert not A.can_rewrite("kimi_code", A.PRE_TOOL)
    assert A.enforcement_level("kimi_code", A.PRE_TOOL) == "best-effort"
    assert "not a sole security barrier" in A.MATRIX["kimi_code"]["notes"]
