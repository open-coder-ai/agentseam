"""Content-comparison identity (opt-in): `installed()` can compare INSTALLED bytes against
the CURRENTLY-COMPILED fragment, not just check for our marker's presence.

Split out of test_install.py to stay under the file-size budget; the fixtures below rely on
the same `I.install`/`I.installed` surface exercised there.
"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentseam import install as I  # noqa: E402


def test_content_match_reads_as_installed(tmp_path):
    """The marker-presence default answers "did we write something here"; content mode
    answers "does what's here still match what we'd write right now" -- for an unchanged
    fragment those agree.
    """
    root = str(tmp_path)
    I.install("claude_code", ["pre_tool"], "guard.py", root, matcher="Write|Edit")
    assert I.installed("claude_code", root, events=["pre_tool"], command="guard.py", matcher="Write|Edit")


def test_content_drift_reads_as_not_installed(tmp_path):
    """A real historical bug (documented on chock's `installed_pretooluse_policy_ids`): a
    stale hook whose guard changed kept reading as "enforced" under marker-presence alone.
    Content mode must catch exactly this -- the installed bytes no longer match what the
    currently-compiled fragment would be, so the claim must drop until re-sync.
    """
    root = str(tmp_path)
    I.install("claude_code", ["pre_tool"], "guard.py", root, matcher="Write|Edit")

    # Marker-presence (default) still says yes: something we wrote is there.
    assert I.installed("claude_code", root)
    # But the guard's own source changed underneath it (recompiled to a new command) --
    # content mode must say the INSTALLED entry no longer matches.
    assert not I.installed("claude_code", root, events=["pre_tool"], command="guard-v2.py", matcher="Write|Edit")
    # A changed matcher is drift too, not just a changed command.
    assert not I.installed("claude_code", root, events=["pre_tool"], command="guard.py", matcher="Write|Edit|Bash")


def test_content_comparison_before_any_install_is_not_installed(tmp_path):
    root = str(tmp_path)
    assert not I.installed("claude_code", root, events=["pre_tool"], command="guard.py")


def test_reinstall_converges_under_content_comparison(tmp_path):
    """After a drift is detected, re-running install() must make content mode agree with
    marker-presence again -- the whole point of "re-sync" being a real, working recovery.
    """
    root = str(tmp_path)
    I.install("claude_code", ["pre_tool"], "guard.py", root, matcher="Write|Edit")
    assert not I.installed("claude_code", root, events=["pre_tool"], command="guard-v2.py", matcher="Write|Edit")

    I.install("claude_code", ["pre_tool"], "guard-v2.py", root, matcher="Write|Edit")
    assert I.installed("claude_code", root, events=["pre_tool"], command="guard-v2.py", matcher="Write|Edit")
    assert not I.installed("claude_code", root, events=["pre_tool"], command="guard.py", matcher="Write|Edit")


def test_content_comparison_default_mode_is_unchanged(tmp_path):
    """Omitting events/command must behave exactly as before: presence, not content."""
    root = str(tmp_path)
    I.install("claude_code", ["pre_tool"], "guard.py", root, matcher="Write|Edit")
    assert I.installed("claude_code", root)  # unaffected by any of the above content checks
    I.install("claude_code", ["pre_tool"], "guard-v2.py", root, matcher="Write|Edit")
    assert I.installed("claude_code", root)  # still just "we wrote something", now the new one


def test_content_comparison_needs_both_events_and_command(tmp_path):
    with pytest.raises(ValueError):
        I.installed("claude_code", str(tmp_path), events=["pre_tool"])
    with pytest.raises(ValueError):
        I.installed("claude_code", str(tmp_path), command="guard.py")


def test_content_comparison_works_on_the_toml_block_format_too(tmp_path, monkeypatch):
    """Codex/kimi_code write a marker-delimited block into a TOML file we cannot merge
    into -- content mode there is a text comparison of that block, not a structural one.
    """
    monkeypatch.setenv("HOME", str(tmp_path))
    I.install("kimi_code", ["pre_tool"], "guard.py", str(tmp_path))
    assert I.installed("kimi_code", str(tmp_path), events=["pre_tool"], command="guard.py")
    assert not I.installed("kimi_code", str(tmp_path), events=["pre_tool"], command="guard-v2.py")

    I.install("kimi_code", ["pre_tool"], "guard-v2.py", str(tmp_path))
    assert I.installed("kimi_code", str(tmp_path), events=["pre_tool"], command="guard-v2.py")


def test_content_comparison_is_specific_to_our_own_owner(tmp_path):
    """Two owners' fragments must not be confused with each other under content mode."""
    root = str(tmp_path)
    I.install("cursor", ["pre_tool"], "guard-A", repo_root=root, owner="team-a")
    I.install("cursor", ["pre_tool"], "guard-B", repo_root=root, owner="team-b")
    assert I.installed("cursor", root, owner="team-a", events=["pre_tool"], command="guard-A")
    assert not I.installed("cursor", root, owner="team-a", events=["pre_tool"], command="guard-B")
    assert I.installed("cursor", root, owner="team-b", events=["pre_tool"], command="guard-B")


def test_content_comparison_rejects_an_event_this_agent_cannot_wire(tmp_path):
    """Mirrors install()'s own validation -- an unwireable event is a caller mistake to
    surface, not something to answer False about as if it were merely absent."""
    with pytest.raises(ValueError):
        I.installed("codex_cli", str(tmp_path), events=["not_a_real_event"], command="guard.py")
