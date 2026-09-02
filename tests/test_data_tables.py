"""The evidence-note data tables: schema-validated, consistent with the code reading them."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from validate_vendor_config import validate  # noqa: E402

from agentseam._data import load  # noqa: E402
from agentseam.packaging_data import PACKAGING, PARTS  # noqa: E402
from agentseam.permissions_data import CAPABILITY  # noqa: E402
from agentseam.permissions_render import _CONTENT_REASON  # noqa: E402

TABLES = {
    "allow-semantics.json": "allow-semantics.schema.json",
    "packaging-limits.json": "packaging-limits.schema.json",
    "permissions-content-reasons.json": "permissions-content-reasons.schema.json",
}


@pytest.mark.parametrize("table", sorted(TABLES))
def test_schema_validates_every_committed_table(table):
    assert validate(load(TABLES[table]), load(table)) == []


def test_schema_rejects_an_unknown_bare_allow_kind():
    mutated = copy.deepcopy(load("allow-semantics.json"))
    mutated["semantics"]["cursor"]["bare_allow"] = "probably-fine"
    assert validate(load(TABLES["allow-semantics.json"]), mutated) != []


def test_schema_rejects_a_basis_outside_the_closed_vocabulary():
    mutated = copy.deepcopy(load("allow-semantics.json"))
    mutated["semantics"]["cursor"]["basis"] = "trust me"
    assert validate(load(TABLES["allow-semantics.json"]), mutated) != []


def test_schema_rejects_an_empty_note():
    mutated = copy.deepcopy(load("allow-semantics.json"))
    mutated["semantics"]["grok"]["note"] = ""
    assert validate(load(TABLES["allow-semantics.json"]), mutated) != []


def test_schema_rejects_a_typoed_row_key():
    mutated = copy.deepcopy(load("allow-semantics.json"))
    mutated["semantics"]["claude_code"]["vouches"] = mutated["semantics"]["claude_code"].pop("vouch_speaks")
    assert validate(load(TABLES["allow-semantics.json"]), mutated) != []


def test_schema_rejects_a_typoed_part_name():
    mutated = copy.deepcopy(load("packaging-limits.json"))
    mutated["part_limits"]["cursor"]["skil"] = mutated["part_limits"]["cursor"].pop("subagent")
    assert validate(load(TABLES["packaging-limits.json"]), mutated) != []


def test_schema_rejects_a_content_reason_without_a_note():
    mutated = copy.deepcopy(load("permissions-content-reasons.json"))
    del mutated["claude_code"]["note"]
    assert validate(load(TABLES["permissions-content-reasons.json"]), mutated) != []


def test_schema_still_accepts_a_benign_edit():
    """Reordering keys and lengthening free text change nothing the schema constrains."""
    mutated = copy.deepcopy(load("allow-semantics.json"))
    mutated["semantics"]["grok"]["note"] += " (re-read against a later release, unchanged)"
    mutated["semantics"] = dict(reversed(list(mutated["semantics"].items())))
    assert validate(load(TABLES["allow-semantics.json"]), mutated) == []


def test_the_part_vocabulary_in_the_schema_is_derived_from_the_code():
    """Both per-part maps admit exactly packaging_data.PARTS, bound here so neither drifts."""
    schema = load("packaging-limits.schema.json")
    for shape in ("perPartText", "perPartPaths"):
        assert set(schema["$defs"][shape]["properties"]) == set(PARTS)


def test_part_limits_speak_only_about_recorded_formats():
    """A limit row for an agent with no packaging row would explain a gap in nothing."""
    assert set(load("packaging-limits.json")["part_limits"]) <= set(PACKAGING)


def test_content_reasons_cover_exactly_the_recorded_permission_surfaces():
    assert set(_CONTENT_REASON) == set(CAPABILITY)
