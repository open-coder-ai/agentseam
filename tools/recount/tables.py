"""Judgment calls, stated (dialect-families.md §2.2, §3.1): family assignment, the marker
claims table, and per-claim evidence. Pinned as small tables here rather than mechanically
re-derived -- but every value is checked by a dedicated behavioural test in
tests/test_vendor_config.py, which replays claims()/respond() against synthetic probes built
from exactly these markers.
"""

from __future__ import annotations

from agentseam.matrix_data import MATRIX

_FAMILY = {
    "claude_code": "hook_json",
    "vscode_copilot": "hook_json",
    "codex_cli": "hook_json",
    "kimi_code": "hook_json",
    "devin": "hook_json",
    "gemini_cli": "flat_decision",
    "junie": "flat_decision",
    "tabnine": "flat_decision",
    "grok": "flat_decision",
    "cursor": "cursor",
    "windsurf": "windsurf",
    "antigravity": "antigravity",
}

_SHAPE_INFERRED = frozenset({"cursor", "windsurf", "antigravity"})

_CLAIMS = {
    "claude_code": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "client_types": [None, "claude_code"],
        "reject_markers": ["turn_id", "project_path", "timestamp"],
        "reject_probes": ["looks_like_claude_code"],
        "notes": (
            "prompt_id is rejected only when looks_like_claude_code(raw) is also false "
            "(claude_code.py:79-80); a real Claude Code payload may carry prompt_id and "
            "must still be accepted (matrix-notes.json: fixed 2026-08-27)."
        ),
    },
    "gemini_cli": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "client_types": [None, "gemini_cli", "gemini"],
        "reject_markers": ["timestamp", "project_path", "prompt_id", "turn_id"],
        "reject_probes": ["looks_like_claude_code"],
    },
    "codex_cli": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "accept_markers": ["turn_id"],
        "notes": (
            "Also accepted at SessionStart when session_id, transcript_path, cwd, model, "
            "permission_mode and source are all present (codex_cli.py:35-45); that compound "
            "check is not expressed above."
        ),
    },
    "devin": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "accept_markers": ["prompt_id"],
        "reject_probes": ["looks_like_claude_code"],
        "notes": (
            "PermissionRequest and PostCompaction (devin.py:37) are accepted unconditionally "
            "regardless of markers -- names Claude Code never sends. prompt_id above is "
            "required alongside looks_like_claude_code(raw) being false (devin.py:44-46)."
        ),
    },
    "kimi_code": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "client_types": ["kimi_code_cli"],
    },
    "junie": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "accept_markers": ["project_path"],
    },
    "tabnine": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "accept_markers": ["timestamp"],
        "notes": (
            "timestamp identifies Tabnine but cannot exclude Gemini CLI, which sends it too "
            "(tabnine.py notes); detect() declines when both could claim, and the agent must "
            "be named explicitly."
        ),
    },
    "grok": {
        "mode": "marker",
        "event_key": ["hookEventName"],
    },
    "vscode_copilot": {
        "mode": "marker",
        "event_key": ["hook_event_name", "hookEventName"],
        "accept_markers": ["timestamp"],
        "reject_markers": ["turn_id"],
        "notes": (
            "Accepted three ways (vscode_copilot.py:44-58): (1) a name in EVENT_MAP with the "
            "vscode envelope marker timestamp present and turn_id absent -- the only "
            "unconditional reject, captured above; (2) any lowercase-first event name in "
            "EVENT_MAP (Copilot CLI's own camelCase names), unless permission_mode, model, "
            "cursor_version, conversation_id, generation_id or workspace_roots is present -- "
            "these only reject payloads that fall through to path (2), not every payload, so "
            "they are not listed as unconditional reject_markers; (3) a memory-tool call "
            "carrying tool_input.command."
        ),
    },
}


def family(agent):
    return _FAMILY[agent]


def claims(agent):
    if agent in _SHAPE_INFERRED:
        return {"mode": "shape_inferred"}
    return dict(_CLAIMS[agent])


_EVIDENCE_CLAIMS = ("family", "events", "claims", "fields", "tools", "verdicts", "config_path", "hook_entry")

_EVIDENCE_TEST = {
    "family": "tests/test_golden_fixtures.py::test_wire_output_matches_the_frozen_fixture",
    "events": "tests/test_examples.py::test_each_payload_parses_to_the_event_it_is_filed_under",
    "claims": "tests/test_examples.py::test_each_payload_is_claimed_by_its_own_adapter",
    "fields": "tests/test_vendor_config.py::test_entries_match_recount",
    "tools": "tests/test_vendor_config.py::test_entries_match_recount",
    "verdicts": "tests/test_golden_fixtures.py::test_wire_output_matches_the_frozen_fixture",
    "config_path": "tests/test_vendor_config.py::test_config_path_agrees_with_matrix",
    "hook_entry": "tests/test_golden_fixtures.py::test_hook_config_matches_the_frozen_fixture_on_both_matcher_paths",
}


def evidence(agent):
    """Per-claim evidence (owner decision 2026-09-01, org-plan plan/agentseam-project.md):
    every claim carries `basis` (from matrix_terms.BASES), `date`, and -- since every claim
    group here is exercised by a real automated check -- the test that exercises it. `basis`
    and `date` are the SAME evidence the capability matrix already recorded for this vendor's
    behaviour (matrix-evidence's own verified.basis/date): the config claims above describe
    exactly that behaviour, so inventing a second, unrelated evidence trail for the same facts
    would not be more honest, only duplicated."""
    verified = MATRIX[agent]["verified"]
    return {
        claim: {"basis": verified["basis"], "date": verified["date"], "test": _EVIDENCE_TEST[claim]}
        for claim in _EVIDENCE_CLAIMS
    }
