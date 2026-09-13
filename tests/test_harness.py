"""The harness registry: recorded invocations, refusals, and what voids a run."""

from __future__ import annotations

import json

import pytest

from agentseam import harness, matrix


def test_every_harness_agent_is_a_matrix_row():
    """A harness row for an agent the matrix does not know is a typo, not a new vendor."""
    assert set(harness.HARNESS) <= set(matrix.MATRIX)


def test_prompt_token_is_substituted_not_formatted():
    line = harness.argv("claude_code", "check the page")
    assert harness.PROMPT_PLACEHOLDER not in line
    assert "check the page" in line


def test_a_prompt_containing_braces_survives():
    """Placeholders are replaced, never formatted: a prompt is arbitrary text."""
    prompt = "rename {old} to {new} in the 50% case"
    assert prompt in harness.argv("claude_code", prompt)


def test_model_lands_where_the_vendor_accepts_it():
    """Position is recorded per agent because it cannot be inferred from the argv."""
    codex = harness.argv("codex_cli", "p", model="gpt-5")
    assert codex[:4] == ["codex", "exec", "-m", "gpt-5"]
    claude = harness.argv("claude_code", "p", model="opus")
    assert claude[:3] == ["claude", "--model", "opus"]


def test_model_is_absent_unless_asked_for():
    assert "-m" not in harness.argv("codex_cli", "p")


def test_an_unrecorded_agent_refuses_rather_than_guessing():
    """The invariant this module exists for."""
    with pytest.raises(harness.NoHarnessError) as exc:
        harness.argv("windsurf", "p")
    assert "windsurf" in str(exc.value)


def test_a_missing_hooked_arm_refuses_and_says_why():
    """Falling back to the unhooked argv would silently measure the wrong arm."""
    with pytest.raises(harness.NoHarnessError) as exc:
        harness.argv("codex_cli", "p", hooked=True)
    # The recorded note explains what the hooked arm would need; it is not a shrug.
    assert "hooked_argv" in str(exc.value)
    assert len(str(exc.value)) > len("no 'hooked_argv' recorded for 'codex_cli': ")


def test_an_agent_with_no_model_flag_refuses():
    with pytest.raises(harness.NoHarnessError):
        harness.argv("cursor", "p", model="anything")


def test_void_markers_catch_a_refused_run():
    assert harness.is_void("ERROR: rejected: blocked by policy")
    assert harness.void_reason("sandbox: read-only") == "sandbox: read-only"


def test_void_detection_is_case_insensitive():
    """Vendors capitalise their own errors however they like."""
    assert harness.is_void("Permission Denied")


def test_a_productive_run_is_not_void():
    assert not harness.is_void("edited index.html, added an accessible name")
    assert harness.void_reason("all good") is None


def test_empty_output_is_not_void():
    """Nothing to read is a harness failure to diagnose elsewhere, not vendor refusal."""
    assert not harness.is_void("")
    assert not harness.is_void(None)


def test_instruction_leakage_is_reported_not_assumed_absent():
    leaked = harness.leaked_instructions(harness.INSTRUCTION_MARKERS[0])
    assert leaked
    assert not harness.leaked_instructions("nothing standing here")


def test_isolation_and_ownership_prose_is_available_where_recorded():
    assert harness.isolation("codex_cli")
    assert harness.creates_files_as("codex_cli")
    assert harness.isolation("claude_code") is None


def test_accessors_refuse_for_an_unrecorded_agent():
    with pytest.raises(harness.NoHarnessError):
        harness.isolation("zed")


def test_the_registry_file_is_valid_json_with_every_row_carrying_an_argv():
    """The data file is the artifact a contributor edits; a row without argv is unusable."""
    from agentseam._data import load

    data = load("harness.json")
    assert data["void_markers"]
    for name, record in data["agents"].items():
        assert record.get("argv"), "%s has no argv" % name
        assert any(harness.PROMPT_PLACEHOLDER in part for part in record["argv"]), name
        if "model_argv" in record:
            assert "model_at" in record, "%s: a model flag with no position is unusable" % name
            assert record["model_at"] <= len(record["argv"]), name


def test_json_is_the_only_place_the_invocations_live():
    """No argv is hardcoded in the module: the registry is data the code reads."""
    import pathlib

    source = pathlib.Path(harness.__file__).read_text(encoding="utf-8")
    assert "cursor-agent" not in source
    assert json.dumps(["codex", "exec"])[1:-1] not in source
