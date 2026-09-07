"""Staleness arithmetic, and the one property that matters most: it never over-reassures.

A watcher whose failure mode is silence is worse than no watcher, because silence reads as
"still current". Several tests below exist only to pin that down -- an unreachable feed, an
unknown feed and a version that is not a version must all be visibly distinct from a row
that was genuinely compared and found current.
"""

from __future__ import annotations

import json
import os
from datetime import date

import pytest

from agentseam import staleness
from agentseam._data import load
from agentseam.matrix_evidence import EVIDENCE

TODAY = date(2026, 9, 7)


def _ev(**kw):
    base = {"basis": "live-run", "version": "1.0.0", "date": "2026-09-01"}
    base.update(kw)
    return base


def test_age_days_counts_from_the_recorded_date():
    assert staleness.age_days(_ev(date="2026-09-01"), today=TODAY) == 6


@pytest.mark.parametrize("bad", [None, "", "not-a-date", "2026-13-99"])
def test_age_days_is_none_for_unusable_dates(bad):
    assert staleness.age_days(_ev(date=bad), today=TODAY) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2.1.263", (2, 1, 263)),
        ("0.86.2", (0, 86, 2)),
        ("1.0.0-beta.2", (1, 0, 0)),
        ("v3.17.8", ()),
        ("CLI", ()),
        ("EAP", ()),
        ("", ()),
        (None, ()),
    ],
)
def test_parse_version(text, expected):
    assert staleness.parse_version(text) == expected


@pytest.mark.parametrize(
    ("recorded", "current", "expected"),
    [
        ("2.1.247", "2.1.263", True),
        ("2.1.263", "2.1.263", False),
        ("2.2.0", "2.1.263", False),
        ("1.0", "1.0.1", True),  # differing widths compare by zero-fill
        ("1.0.0", "1.0", False),
        ("CLI", "2.1.263", None),
        ("2.1.247", None, None),
    ],
)
def test_is_behind(recorded, current, expected):
    assert staleness.is_behind(recorded, current) is expected


def test_a_newer_release_is_drift():
    state = staleness.status(_ev(version="2.1.247"), current_version="2.1.263", today=TODAY)
    assert state["verdict"] == staleness.DRIFTED
    assert state["behind"] is True


def test_compared_and_current_is_fresh():
    state = staleness.status(_ev(version="2.1.263"), current_version="2.1.263", today=TODAY)
    assert state["verdict"] == staleness.FRESH


def test_an_uncomparable_row_is_never_fresh():
    """The bug this file was written after: no comparison must not read as 'current'."""
    state = staleness.status(_ev(), current_version=None, today=TODAY)
    assert state["verdict"] == staleness.UNCHECKED
    assert state["verdict"] != staleness.FRESH


def test_prose_where_a_version_belongs_is_flagged():
    """Nine rows record things like 'CLI' or 'EAP'; drift can never be computed for them."""
    state = staleness.status(_ev(version="EAP"), current_version="2026.2.1", today=TODAY)
    assert state["version_comparable"] is False
    assert state["verdict"] != staleness.FRESH


def test_age_beats_recency_but_drift_beats_age():
    old = _ev(date="2026-01-01")
    assert staleness.status(old, current_version="1.0.0", today=TODAY)["verdict"] == staleness.STALE
    # Drifted is the sharper signal, so it wins even though the row is also old.
    assert staleness.status(old, current_version="9.9.9", today=TODAY)["verdict"] == staleness.DRIFTED


def test_documentation_rows_are_unmeasured_not_stale():
    """A vendor-docs row was never a measurement; ageing it would be a category error."""
    for basis in ("vendor-docs", "vendor-source", "third-party-install", "inherited"):
        state = staleness.status(_ev(basis=basis, date="2020-01-01"), today=TODAY)
        assert state["verdict"] == staleness.UNMEASURED, basis


def test_summarize_mentions_the_newer_version():
    state = staleness.status(_ev(version="2.1.247"), current_version="2.1.263", today=TODAY)
    assert "2.1.263 available" in staleness.summarize(state)


def test_every_agent_has_a_release_source_entry():
    """A missing entry is an oversight; a null `kind` is a deliberate, documented gap."""
    sources = load("vendor-releases.json")
    missing = sorted(set(EVIDENCE) - set(sources))
    assert not missing, "no release-source entry for: %s" % ", ".join(missing)


def test_release_sources_without_a_feed_say_why():
    """`kind: null` must carry a note, or it is indistinguishable from someone forgetting."""
    sources = load("vendor-releases.json")
    for agent, entry in sources.items():
        if agent.startswith("_"):
            continue
        if entry.get("kind") is None:
            assert entry.get("note"), "%s has no feed and no explanation" % agent
        else:
            assert entry.get("id"), "%s declares kind=%r with no id" % (agent, entry["kind"])


def test_release_sources_are_declared_as_package_data():
    """Shipped in the wheel, or every install reads an empty table and reports no drift."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "pyproject.toml"), encoding="utf-8") as fh:
        assert "data/*.json" in fh.read()
    assert json.loads(json.dumps(load("vendor-releases.json")))
