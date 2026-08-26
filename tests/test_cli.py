"""CLI behaviour, including the unglamorous parts that make a tool usable."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV = {"PYTHONPATH": str(ROOT / "src"), "PATH": "/usr/bin:/bin:/usr/local/bin"}


def _run(args, **kw):
    return subprocess.run([sys.executable, "-m", "agentseam.cli", *args],
                          capture_output=True, text=True, env=ENV, **kw)


def test_matrix_renders():
    out = _run(["matrix"])
    assert out.returncode == 0
    assert "claude_code" in out.stdout and "enforced" in out.stdout


def test_matrix_survives_a_closed_pipe():
    """`agentseam matrix | head -3` must exit cleanly, not traceback."""
    proc = subprocess.run("%s -m agentseam.cli matrix | head -3" % sys.executable,
                          shell=True, capture_output=True, text=True, env=ENV)
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
    assert "pre_tool=enforced" in out.stdout


def test_install_rejects_unknown_event(tmp_path):
    out = _run(["install", "claude_code", "h", "--events", "bogus_event", "--repo", str(tmp_path)])
    assert out.returncode == 2 and "unknown event" in out.stderr


def test_doctor_runs(tmp_path):
    out = _run(["doctor", "--repo", str(tmp_path)])
    assert "claude_code" in out.stdout and "no hook surface" in out.stdout
