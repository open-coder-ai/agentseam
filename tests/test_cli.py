"""CLI behaviour, including the unglamorous parts that make a tool usable."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin:/usr/local/bin"}


def _run(args, env=None, **kw):
    return subprocess.run(
        [sys.executable, "-m", "agentseam.cli", *args], capture_output=True, text=True, env=env or ENV, **kw
    )


def test_matrix_renders():
    out = _run(["matrix"])
    assert out.returncode == 0
    assert "claude_code" in out.stdout and "enforced" in out.stdout


def test_matrix_survives_a_closed_pipe():
    """`agentseam matrix | head -3` must exit cleanly, not traceback."""
    proc = subprocess.run(
        "%s -m agentseam.cli matrix | head -3" % sys.executable, shell=True, capture_output=True, text=True, env=ENV
    )
    assert proc.returncode == 0
    assert "BrokenPipeError" not in proc.stderr, proc.stderr


def test_agents_and_json_matrix():
    assert "claude_code" in _run(["agents"]).stdout
    import json

    data = json.loads(_run(["matrix", "--json"]).stdout)
    assert data["claude_code"]["tier"] == "block+rewrite"


def test_install_reports_enforcement_level(tmp_path):
    out = _run(["install", "claude_code", "handler.py", "--repo", str(tmp_path)])
    assert out.returncode == 0
    assert "pre_tool=best-effort" in out.stdout


def test_install_rejects_unknown_event(tmp_path):
    out = _run(["install", "claude_code", "h", "--events", "bogus_event", "--repo", str(tmp_path)])
    assert out.returncode == 2 and "unknown event" in out.stderr


def test_doctor_runs(tmp_path):
    out = _run(["doctor", "--repo", str(tmp_path)])
    assert "claude_code" in out.stdout and "no hook surface" in out.stdout


def test_permissions_lists_every_surface_including_the_ones_we_cannot_claim():
    out = _run(["permissions"])
    assert out.returncode == 0
    assert "cannot express" in out.stdout  # VS Code has no deny to offer
    assert "no permission model recorded" in out.stdout
    # Every agent the matrix knows appears, recorded or named as unrecorded.
    for agent in ("cursor", "aider", "zed", "junie", "kimi_code"):
        assert agent in out.stdout, agent


def test_long_unrecorded_reasons_are_wrapped_rather_than_run_off_the_terminal():
    out = _run(["permissions"])
    assert max(len(line) for line in out.stdout.splitlines()) <= 100


def test_permissions_exits_nonzero_when_a_rule_would_not_be_enforced():
    """The exit code is the CI-usable answer: did my policy survive the trip to this agent?"""
    enforced = _run(["permissions", "--rule", "deny:shell:curl *", "--agents", "claude_code"])
    assert enforced.returncode == 0

    lost = _run(["permissions", "--rule", "deny:shell:curl *", "--agents", "vscode_copilot"])
    assert lost.returncode == 1
    assert "unrepresentable" in lost.stdout


def test_permissions_rejects_a_malformed_rule():
    out = _run(["permissions", "--rule", "shell"])
    assert out.returncode == 2
    assert "action:capability" in out.stderr


def test_packaging_shows_the_layouts_and_what_is_shared():
    out = _run(["packaging"])
    assert out.returncode == 0
    assert "skills/{name}/SKILL.md" in out.stdout
    assert "write once, works for several" in out.stdout
    assert "also reads another agent's" in out.stdout
    assert "codex_cli" in out.stdout  # named as unrecorded, with the reason


def test_install_all_skips_unwireable_agents_and_says_so(tmp_path):
    """Both documented example commands used to crash with a traceback and wire NOTHING.

    At least one of twelve agents lacks a hook for any given event set, and install()
    raising for it is deliberate -- but `all` propagating that raise meant the eleven
    wireable agents were taken down by the one gap. The permissions primitive already
    solved this shape: do what can be done, name what cannot, exit non-zero.
    """
    out = _run(
        [
            "install",
            "all",
            "echo hi",
            "--events",
            "pre_tool",
            "post_tool",
            "session_start",
            "stop",
            "--repo",
            str(tmp_path),
        ],
        env={**ENV, "HOME": str(tmp_path)},  # kimi's config is user-scoped; keep it in the sandbox
    )

    assert out.returncode == 1, "a skipped agent must be visible to CI: %s" % out.stderr
    for agent in ("claude_code", "cursor", "gemini_cli", "grok"):
        assert "wired %-16s" % agent in out.stdout
    for agent in ("antigravity", "junie", "vscode_copilot", "windsurf"):
        assert ("skipped %-14s" % agent) in out.stderr, "%s should be skipped whole" % agent
    assert "no hook for" in out.stderr

    # And the wireable agents really were wired -- the skip must not have aborted the loop.
    sys.path.insert(0, str(ROOT / "src"))
    from agentseam import install as install_mod

    assert install_mod.installed("cursor", str(tmp_path))
    assert install_mod.installed("windsurf", str(tmp_path)) is False
