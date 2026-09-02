"""D2 (dialect-families.md §6): the vendor config schema, the 12 entries, and §5.1-2/§3.3.

Schema validation is a TEST, not a runtime cost (§3.3): `agentseam.vendor_config` loads the
committed JSON at import time, unvalidated, and this file is where `schema.json` actually
gets executed against every entry.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

from recount import build_all  # noqa: E402
from validate_vendor_config import validate  # noqa: E402

from agentseam import adapters  # noqa: E402
from agentseam.matrix_data import MATRIX  # noqa: E402
from agentseam.vendor_config import SCHEMA, VENDOR_CONFIG  # noqa: E402

AGENTS = sorted(adapters.ADAPTERS)


# ---------------------------------------------------------------------------------------
# Schema validation, and the mutation pass (worker-protocol.md: "mutation-test the benign
# edit too, and do not call the mutation pass sufficient").
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("agent", AGENTS)
def test_schema_validates_every_committed_entry(agent):
    assert validate(SCHEMA, VENDOR_CONFIG[agent]) == []


def test_schema_rejects_a_missing_evidence_claim():
    """Owner decision 2026-09-01: schema validation FAILS a claim with no basis."""
    mutated = copy.deepcopy(VENDOR_CONFIG["gemini_cli"])
    del mutated["evidence"]["fields"]
    assert validate(SCHEMA, mutated) != []


def test_schema_rejects_a_basis_outside_the_closed_vocabulary():
    mutated = copy.deepcopy(VENDOR_CONFIG["gemini_cli"])
    mutated["evidence"]["fields"]["basis"] = "trust me"
    assert validate(SCHEMA, mutated) != []


def test_schema_rejects_an_unknown_top_level_key():
    mutated = copy.deepcopy(VENDOR_CONFIG["gemini_cli"])
    mutated["bogus"] = True
    assert validate(SCHEMA, mutated) != []


def test_schema_rejects_an_unknown_gate_grammar():
    mutated = copy.deepcopy(VENDOR_CONFIG["claude_code"])
    mutated["verdicts"]["gates"]["PreToolUse"]["grammar"] = "G9"
    assert validate(SCHEMA, mutated) != []


def test_schema_rejects_a_typoed_gate_field_name():
    """Field names follow the post-W35 ACS vocabulary (escalate/transform); a reviewer's
    typo back to the pre-ACS ask/rewrite spelling must fail loud, not fail open."""
    mutated = copy.deepcopy(VENDOR_CONFIG["claude_code"])
    gate = mutated["verdicts"]["gates"]["PreToolUse"]
    gate["honours_ask"] = gate.pop("honours_escalate")
    assert validate(SCHEMA, mutated) != []


def test_schema_rejects_an_unrecognised_claims_mode():
    mutated = copy.deepcopy(VENDOR_CONFIG["cursor"])
    mutated["claims"]["mode"] = "psychic"
    assert validate(SCHEMA, mutated) != []


def test_schema_rejects_an_unknown_word_key():
    """The engine looks words up by concept; a typo'd concept would silently never speak."""
    mutated = copy.deepcopy(VENDOR_CONFIG["claude_code"])
    mutated["verdicts"]["words"]["ask"] = "ask"
    assert validate(SCHEMA, mutated) != []


def test_schema_rejects_an_unknown_degrade_note_key():
    mutated = copy.deepcopy(VENDOR_CONFIG["codex_cli"])
    mutated["verdicts"]["degrade_notes"]["rewrite"] = "typo'd concept"
    assert validate(SCHEMA, mutated) != []


def test_schema_rejects_a_marker_claims_entry_missing_event_key():
    """The one `if`/`then` branch in the schema: mode=="marker" requires event_key."""
    mutated = copy.deepcopy(VENDOR_CONFIG["gemini_cli"])
    del mutated["claims"]["event_key"]
    assert validate(SCHEMA, mutated) != []


def test_schema_rejects_a_non_string_repo_root_token():
    """The token is a config-line string (dialect-families.md §3); a list or map is a typo."""
    mutated = copy.deepcopy(VENDOR_CONFIG["claude_code"])
    mutated["repo_root_token"] = ["${CLAUDE_PROJECT_DIR}"]
    assert validate(SCHEMA, mutated) != []


def test_schema_still_accepts_a_benign_edit():
    """A guard nobody has watched pass a legitimate change only teaches people to route
    around it (worker-protocol.md). Reordering keys and lengthening free text change
    nothing the schema constrains."""
    mutated = copy.deepcopy(VENDOR_CONFIG["gemini_cli"])
    mutated["display"] = "Gemini CLI (renamed in a future release)"
    mutated["evidence"] = dict(reversed(list(mutated["evidence"].items())))
    assert validate(SCHEMA, mutated) == []


# ---------------------------------------------------------------------------------------
# §3: entries recount against the adapters -- never transcribed by hand.
# ---------------------------------------------------------------------------------------


@pytest.mark.parametrize("agent", AGENTS)
def test_entries_match_recount(agent):
    """`tools/recount_vendor_config.py` re-derived, fresh, must equal the committed JSON."""
    from agentseam._data import _tuples

    assert VENDOR_CONFIG[agent] == _tuples(build_all()[agent])


# ---------------------------------------------------------------------------------------
# §3.3: config gates are a subset of matrix block-capable events; config_path agrees.
# ---------------------------------------------------------------------------------------


def _canonical_of(entry, vendor_name):
    if vendor_name in entry["events"]:
        return entry["events"][vendor_name]
    for canonical, name in entry.get("wire_events", {}).items():
        if name == vendor_name:
            return canonical
    return None


@pytest.mark.parametrize("agent", AGENTS)
def test_config_gates_are_a_subset_of_matrix_block_capable_events(agent):
    entry = VENDOR_CONFIG[agent]
    offenders = []
    for vendor_name in entry["verdicts"]["gates"]:
        canonical = _canonical_of(entry, vendor_name)
        assert canonical is not None, "%s: gate %r maps to no canonical event" % (agent, vendor_name)
        if not (MATRIX[agent]["events"].get(canonical) or {}).get("block"):
            offenders.append("%s/%s -> %s (matrix block=False)" % (agent, vendor_name, canonical))
    assert not offenders, "\n".join(offenders)


@pytest.mark.parametrize("agent", AGENTS)
def test_config_path_agrees_with_matrix(agent):
    from fnmatch import fnmatch

    matrix_config = MATRIX[agent]["config"]
    config_path = VENDOR_CONFIG[agent]["config_path"]
    assert config_path == matrix_config or fnmatch(config_path, matrix_config)


# ---------------------------------------------------------------------------------------
# repo_root_token (post-C2 data gap): opt-in, primary-sourced, and never without evidence.
# ---------------------------------------------------------------------------------------


def test_repo_root_token_is_recorded_only_where_primary_sourced():
    """recount/sourced.py cites the vendor doc; absence means not established, not no token."""
    carrying = {a for a in AGENTS if "repo_root_token" in VENDOR_CONFIG[a]}
    assert carrying == {"claude_code"}
    assert VENDOR_CONFIG["claude_code"]["repo_root_token"] == "${CLAUDE_PROJECT_DIR}"


@pytest.mark.parametrize("agent", AGENTS)
def test_repo_root_token_travels_with_its_own_evidence(agent):
    """The schema cannot express the pairing (its validator has no dependentRequired), so
    it is pinned here: the field and its evidence record appear together or not at all."""
    entry = VENDOR_CONFIG[agent]
    assert ("repo_root_token" in entry) == ("repo_root_token" in entry["evidence"])


# ---------------------------------------------------------------------------------------
# §5.1: vocabulary_basis re-homes test_the_unverified_vocabulary_is_still_only_tabnine's
# intent as a fact about this config, not a source-file grep (dialect-families.md §5 table).
# ---------------------------------------------------------------------------------------


def test_vocabulary_basis_is_unverified_only_for_tabnine():
    unverified = {a for a in AGENTS if VENDOR_CONFIG[a]["verdicts"]["vocabulary_basis"] == "unverified"}
    assert unverified == {"tabnine"}


# ---------------------------------------------------------------------------------------
# §7 [h]: the reject_probes device, and the loader's tuple-restore.
# ---------------------------------------------------------------------------------------


def test_reject_probes_stay_under_the_three_probe_budget():
    """[h]: "if D2 finds more than ~3 named probes are needed, [the design] should be
    revisited rather than the list grown." Recounted: exactly one (looks_like_claude_code),
    used by three vendors -- reject_markers_unless_probe cites the same predicate, so its
    keys count toward the same budget."""
    probes = {p for entry in VENDOR_CONFIG.values() for p in entry["claims"].get("reject_probes", [])}
    probes |= {p for entry in VENDOR_CONFIG.values() for p in entry["claims"].get("reject_markers_unless_probe", {})}
    assert probes == {"looks_like_claude_code"}


def test_loader_tuple_restore_preserves_field_chain_order():
    """[h]: PR #89's loader restores every JSON array as a tuple; `fields` chains are
    order-sensitive. A tuple preserves the exact sequence its JSON array was written in, so
    the restore is order-safe -- demonstrated here against a real multi-candidate chain
    rather than merely asserted."""
    chain = VENDOR_CONFIG["gemini_cli"]["fields"]["path"]
    assert isinstance(chain, tuple)
    assert chain == ("tool_input.file_path", "tool_input.absolute_path", "tool_input.path")
