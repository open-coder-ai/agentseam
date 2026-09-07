"""Recording format: schema-validated, and immutable by filename convention.

A recording is what tools/experiment.py --record freezes from a real agent run. Nothing
here exercises the harness itself (tests/test_recorded_driver.py does that) -- this is
purely about the data shape, the same split test_data_tables.py draws for every other table.
"""

from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from validate_vendor_config import validate  # noqa: E402

from agentseam import recordings  # noqa: E402
from agentseam._data import load  # noqa: E402

RECORDINGS_DIR = ROOT / "src" / "agentseam" / "data" / "recordings"
SCHEMA = load("recordings/schema.json")


def _committed_recordings():
    return sorted(p.name for p in RECORDINGS_DIR.glob("*.json") if p.name != "schema.json")


@pytest.mark.parametrize("name", _committed_recordings())
def test_schema_validates_every_committed_recording(name):
    assert validate(SCHEMA, load("recordings/%s" % name)) == []


@pytest.mark.parametrize("name", _committed_recordings())
def test_filename_matches_the_recording_it_names(name):
    """The immutability rule (a newer version is a new file) rests on this holding."""
    body = load("recordings/%s" % name)
    assert name == "%s@%s.json" % (body["agent"], body["version"])


def _seed():
    with open(RECORDINGS_DIR / "claude_code@2.1.263.json", encoding="utf-8") as fh:
        return json.load(fh)


def test_a_missing_required_header_field_fails_by_name():
    mutated = copy.deepcopy(_seed())
    del mutated["driver"]
    errors = validate(SCHEMA, mutated)
    assert any("driver" in e for e in errors)


def test_a_trial_missing_hook_invocations_fails_by_name():
    mutated = copy.deepcopy(_seed())
    del mutated["events"]["pre_tool"]["trials"]["deny"]["hook_invocations"]
    errors = validate(SCHEMA, mutated)
    assert any("hook_invocations" in e for e in errors)


def test_an_unrecognised_driver_value_is_rejected():
    mutated = copy.deepcopy(_seed())
    mutated["driver"] = "reference"
    errors = validate(SCHEMA, mutated)
    assert any("driver" in e for e in errors)


def test_an_extra_top_level_field_is_rejected():
    mutated = copy.deepcopy(_seed())
    mutated["basis"] = "live-run"
    errors = validate(SCHEMA, mutated)
    assert any("basis" in e for e in errors)


def test_benign_edits_still_pass():
    """Reordering keys and adding the optional reporter/notes fields change nothing constrained."""
    mutated = copy.deepcopy(_seed())
    mutated["reporter"] = "@someone"
    mutated = dict(reversed(list(mutated.items())))
    assert validate(SCHEMA, mutated) == []


def test_recordings_reader_finds_the_seeded_claude_code_version():
    assert "2.1.263" in recordings.versions("claude_code")
    assert recordings.latest_version("claude_code") == "2.1.263"
    assert os.path.exists(recordings.path_for("claude_code", "2.1.263"))


def test_recordings_reader_returns_none_for_an_agent_never_witnessed():
    assert recordings.latest_version("no-such-agent") is None
    assert recordings.load_recording("no-such-agent") is None
