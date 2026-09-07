"""CLI behaviour, including the unglamorous parts that make a tool usable."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin:/usr/local/bin"}


def home_env(path):
    """Every variable `os.path.expanduser` might consult, pointed at `path`.

    Setting only HOME is a POSIX-shaped assumption. `ntpath.expanduser` reads USERPROFILE,
    then HOMEDRIVE+HOMEPATH, and never looks at HOME at all -- so on Windows, a test that
    replaces the environment and sets only HOME leaves expanduser with nothing to expand.
    It then returns "~" unchanged, and any agent whose config_path starts with "~" (kimi
    code: `~/.kimi-code/config.toml`) gets a directory literally named `~` in the CWD.

    The production expansion in install_config.resolve() is correct; it was the test's
    environment that had no Windows home in it.
    """
    path = str(path)
    drive, tail = os.path.splitdrive(path)
    return {"HOME": path, "USERPROFILE": path, "HOMEDRIVE": drive, "HOMEPATH": tail or path}


def _run(args, env=None, **kw):
    return subprocess.run(
        [sys.executable, "-m", "agentseam.cli", *args], capture_output=True, text=True, env=env or ENV, **kw
    )


def test_matrix_renders():
    out = _run(["matrix"])
    assert out.returncode == 0
    assert "claude_code" in out.stdout and "best-effort" in out.stdout


def test_matrix_evidence_shows_the_recorded_version_beside_the_rows():
    out = _run(["matrix", "--evidence"])
    assert out.returncode == 0
    line = next(row for row in out.stdout.splitlines() if row.startswith("claude_code "))
    assert "2.1.247" in line  # the row's own verified.version
    assert "2.1.263" in line  # the newest committed recording


#: A portable `head -3`: read three lines, then exit and drop the read end of the pipe.
#: Spawned rather than shelled out to because Windows has no `head`.
_HEAD_3 = "import sys\nfor _ in range(3): sys.stdin.readline()\n"


def test_matrix_survives_a_closed_pipe():
    """A reader that walks away mid-stream must not become a BrokenPipeError traceback.

    Built as a real two-process pipeline rather than `| head -3` so it runs on Windows,
    which has no `head` and no POSIX shell. The guarantee is unchanged: something reads
    the first few lines and then closes the pipe while the CLI may still be writing.

    Whether the CLI is *still* writing at that moment depends on the pipe buffer, so this
    is a regression guard rather than a deterministic reproduction -- as it was before.
    """
    # The pipe is made here rather than by Popen so the producer has no `stdout` attribute for
    # communicate() to read later: on Windows that reads a closed file from a thread and leaks
    # an unhandled-thread-exception warning into the run.
    read_end, write_end = os.pipe()
    producer = subprocess.Popen(
        [sys.executable, "-m", "agentseam.cli", "matrix"], stdout=write_end, stderr=subprocess.PIPE, env=ENV
    )
    reader = subprocess.Popen([sys.executable, "-c", _HEAD_3], stdin=read_end, stdout=subprocess.DEVNULL, env=ENV)
    # Only the children may hold the pipe, or it never breaks when the reader exits.
    os.close(read_end)
    os.close(write_end)
    reader.wait(timeout=30)
    _, err = producer.communicate(timeout=30)

    stderr = err.decode("utf-8", "replace")
    assert producer.returncode == 0, stderr
    assert "BrokenPipeError" not in stderr, stderr


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
    assert "cannot express" in out.stdout
    assert "no permission model recorded" in out.stdout
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
    assert "codex_cli" in out.stdout


def test_install_all_skips_unwireable_agents_and_says_so(tmp_path):
    """Both documented example commands used to crash with a traceback and wire NOTHING."""
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
        env={**ENV, **home_env(tmp_path)},
        cwd=str(tmp_path),
    )

    assert out.returncode == 1, "a skipped agent must be visible to CI: %s" % out.stderr
    for agent in ("claude_code", "cursor", "gemini_cli", "grok", "vscode_copilot"):
        assert "wired %-16s" % agent in out.stdout
    for agent in ("antigravity", "junie", "windsurf"):
        assert ("skipped %-14s" % agent) in out.stderr, "%s should be skipped whole" % agent
    assert "no hook for" in out.stderr

    sys.path.insert(0, str(ROOT / "src"))
    from agentseam import install as install_mod

    assert install_mod.installed("cursor", str(tmp_path))
    assert install_mod.installed("windsurf", str(tmp_path)) is False
