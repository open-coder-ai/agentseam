"""`tools/capture_fixtures.py` is reproducible: a re-run leaves every golden fixture byte-identical.

The replay test (`test_golden_fixtures.py`) only replays each fixture's own payload, so a
payload that drifted from `examples/scenarios.py` went unnoticed; these tests close that gap.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import capture_fixtures as C  # noqa: E402

from agentseam import adapters  # noqa: E402

AGENTS = sorted(adapters.ADAPTERS)


@pytest.mark.parametrize("agent", AGENTS)
def test_committed_fixture_is_exactly_what_capture_writes(agent):
    """Byte-for-byte: a capture on a clean checkout must leave no diff."""
    committed = Path(C.fixture_path(agent)).read_bytes().decode("utf-8")
    assert committed == C.render(agent), "re-run tools/capture_fixtures.py and review the diff"


@pytest.mark.parametrize("agent", AGENTS)
def test_two_captures_in_one_process_are_identical(agent):
    assert C.render(agent) == C.render(agent)


def _write_lf(path, text):
    """Text-mode write_text would turn \\n into \\r\\n on Windows and make every fixture look drifted."""
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def test_check_flags_a_drifted_and_a_missing_fixture(tmp_path):
    first, second, *rest = AGENTS
    for agent in rest:
        _write_lf(C.fixture_path(agent, tmp_path), C.render(agent))
    _write_lf(C.fixture_path(first, tmp_path), C.render(first).replace("example", "drift"))
    assert C.drifted(tmp_path) == [first, second]


@pytest.mark.parametrize("seed", ["0", "4242"])
def test_check_passes_in_a_fresh_interpreter_under_any_hash_seed(seed):
    """Set and dict ordering must not leak into the bytes."""
    env = dict(os.environ, PYTHONHASHSEED=seed)
    proc = subprocess.run(  # noqa: S603
        [sys.executable, "-W", "ignore", str(ROOT / "tools" / "capture_fixtures.py"), "--check"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_unknown_arguments_are_refused_without_writing():
    assert C.main(["--bogus"]) == 2
