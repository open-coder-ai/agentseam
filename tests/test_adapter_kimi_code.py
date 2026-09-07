"""Kimi Code adapter: three blocking events out of twenty, and a TOML config."""

import json
import sys
from pathlib import Path

import pytest

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
    assert body == {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "test-deny",
    }
    assert code == 0


def test_a_write_payload_exposes_its_path_and_content():
    _, _, event, _ = A.handle(KM_WRITE, deny_all)
    assert event.path == "AGENTS.md" and "AWS_SECRET" in event.content


def test_observation_only_events_stay_silent():
    """Documented as fire-and-forget: a decision there would read as a gate that isn't one."""
    for payload in (KM_POST, KM_NOTIFY):
        text, code, _, _ = A.handle(payload, deny_all)
        assert (text, code) == ("", 0)


def test_multiedit_and_notebookedit_content_reach_a_content_policy():
    """The docstring stakes everything on this envelope being Claude Code's exactly (same"""
    multiedit = dict(KM_WRITE)
    multiedit["tool_name"] = "MultiEdit"
    multiedit["tool_input"] = {
        "file_path": "AGENTS.md",
        "edits": [{"old_string": "x", "new_string": "AWS_SECRET_ACCESS_KEY=akia"}],
    }
    _, _, event, _ = A.handle(multiedit, deny_all)
    assert "AWS_SECRET_ACCESS_KEY" in event.content

    notebook = dict(KM_WRITE)
    notebook["tool_name"] = "NotebookEdit"
    notebook["tool_input"] = {"notebook_path": "nb.ipynb", "new_source": "SECRET=akia"}
    _, _, event, _ = A.handle(notebook, deny_all)
    assert event.path == "nb.ipynb" and "SECRET" in event.content


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


def test_install_appends_a_block_and_leaves_the_users_settings_untouched(tmp_path, isolated_home):
    """config.toml is the user's whole CLI configuration, not a hooks file.

    Home comes from the `isolated_home` fixture: kimi_code's config is user-scoped, and a
    local setenv("HOME") is read by posixpath only, so the seeded file sat where no install
    would look and the "left untouched" assertion was reading an untouched file."""
    config = isolated_home / ".kimi-code" / "config.toml"
    config.parent.mkdir(parents=True)
    original = '[model]\nname = "kimi-k2"\n\n[[hooks]]\nevent = "Stop"\ncommand = "mine.sh"\n'
    config.write_text(original)

    I.install("kimi_code", ["pre_tool"], "guard.py", str(tmp_path))
    after = config.read_text()
    assert original.strip() in after
    assert "guard.py" in after and I.installed("kimi_code", str(tmp_path))

    assert I.uninstall("kimi_code", str(tmp_path)) is True
    assert config.read_text().strip() == original.strip()
    assert I.installed("kimi_code", str(tmp_path)) is False


def test_reinstalling_replaces_our_block_rather_than_stacking_them(tmp_path, isolated_home):
    """Home is the fixture's, not a local setenv("HOME"): the file both installs actually
    wrote lives under the home expanduser resolves, which on Windows is never HOME."""
    I.install("kimi_code", ["pre_tool"], "first.py", str(tmp_path))
    I.install("kimi_code", ["pre_tool"], "second.py", str(tmp_path))
    text = (isolated_home / ".kimi-code" / "config.toml").read_text()
    assert text.count(I.BEGIN) == 1
    assert "second.py" in text and "first.py" not in text


def test_the_config_is_user_scoped_not_repository_scoped():
    """Kimi reads one settings file per user; a repo-local config.toml is read by nothing."""
    assert A.adapters.get("kimi_code").CONFIG_PATH.startswith("~/")


def test_kimi_blocks_but_fails_open_and_the_notes_say_not_to_rely_on_it():
    assert A.can_block("kimi_code", A.PRE_TOOL)
    assert not A.can_rewrite("kimi_code", A.PRE_TOOL)
    assert A.enforcement_level("kimi_code", A.PRE_TOOL) == "best-effort"
    assert "not a sole security barrier" in A.MATRIX["kimi_code"]["notes"]


def test_post_compact_is_not_bent_into_pre_compact():
    """PostCompact fires AFTER compaction; a pre_compact policy exists to run BEFORE it."""
    mod = A.adapters.get("kimi_code")
    post = {"hook_event_name": "PostCompact", "client_type": "kimi_code_cli"}
    assert mod.parse(post).event == A.UNKNOWN
    assert mod.parse({"hook_event_name": "PreCompact", "client_type": "kimi_code_cli"}).event == A.PRE_COMPACT
    assert mod.REVERSE_EVENT_MAP[A.PRE_COMPACT] == "PreCompact"
    assert mod.claims(post), "unmapping must not blind a caller to the payload"


def test_an_unmapped_event_from_a_self_identified_payload_is_still_kimi():
    """client_type is Kimi's whole detection, so a name it has not mapped yet is Kimi's too:"""
    novel = {"client_type": "kimi_code_cli", "hook_event_name": "TurnStarted"}
    mod = A.adapters.get("kimi_code")
    assert mod.claims(novel) and mod.parse(novel).event == A.UNKNOWN
    _, code, event, _ = A.handle(novel, lambda _e: Decision.deny("x"))
    assert (event.agent, event.event, code) == ("kimi_code", A.UNKNOWN, 0)


def test_accept_any_name_rests_on_client_type_never_being_absent():
    """The opt-in is safe only because a payload without client_type is not claimed at all."""
    claims = A.adapters.get("kimi_code").CONFIG["claims"]
    assert claims["accept_any_name"] and None not in claims["client_types"]
    assert not A.adapters.get("kimi_code").claims({"hook_event_name": "TurnStarted"})


#: A command a shell wrapper or an awkward path could carry: quote, newline, CR, tab, and a
#: bare C0 control. The newline is the one that matters -- it ends the TOML line, so the rest
#: lands as extra bare keys in a table the vendor documents as taking four fields only.
_HOSTILE_COMMAND = 'py -c "x"\nevil = 1\ttab\rcr\x01ctl'


def test_a_control_character_in_the_command_still_renders_one_key_per_line():
    """Kimi rejects the WHOLE config.toml over one bad entry, so an unescaped newline does"""
    mod = A.adapters.get("kimi_code")
    rules = mod.hook_config([A.PRE_TOOL], _HOSTILE_COMMAND, matcher="Bash")
    block = mod.render_config(rules).strip()
    assert len(block.splitlines()) == 1 + len(rules[0]), block
    assert not [ch for ch in block.replace("\n", "") if ch < " "], block


@pytest.mark.skipif(sys.version_info < (3, 11), reason="tomllib arrived in 3.11")
def test_the_rendered_block_parses_back_to_the_rules_it_was_given():
    """The derivation: a real TOML parser must return exactly what hook_config produced."""
    import tomllib

    mod = A.adapters.get("kimi_code")
    rules = mod.hook_config([A.PRE_TOOL, A.STOP], _HOSTILE_COMMAND, matcher="Bash|Edit")
    assert tomllib.loads(mod.render_config(rules))["hooks"] == list(rules)
