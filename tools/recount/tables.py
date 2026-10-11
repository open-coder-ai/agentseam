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
    "goose": "flat_decision",
    "openhands": "flat_decision",
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
        "reject_markers_unless_probe": {"looks_like_claude_code": ["prompt_id"]},
        "notes": (
            "prompt_id rejects only when looks_like_claude_code(raw) is also false; a real "
            "Claude Code payload may carry prompt_id and must still be accepted "
            "(matrix-notes.json: fixed 2026-08-27)."
        ),
    },
    "gemini_cli": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "client_types": [None, "gemini_cli", "gemini"],
        "reject_markers": ["timestamp", "project_path", "prompt_id", "turn_id"],
        "reject_probes": ["looks_like_claude_code"],
        "notes": "timestamp is in Gemini's documented base input too: rejecting it is a deliberate tie-break "
        "toward Tabnine, which sends the same shape and whose deny/allow wire is identical (ask/transform "
        "degrade to deny); a declining detect() would allow silently. Name gemini_cli to get ask/transform.",
    },
    "codex_cli": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "accept_markers": ["turn_id"],
        "accept_when_all": {
            "SessionStart": ["session_id", "transcript_path", "cwd", "model", "permission_mode", "source"]
        },
        "notes": (
            "Codex sends no turn_id at SessionStart, so that one event is claimed by the "
            "accept_when_all compound instead (confirmed live 2026-08-28)."
        ),
    },
    "devin": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "accept_markers": ["prompt_id"],
        "accept_names": ["PostCompaction"],
        "reject_client_types": ["kimi_code_cli"],
        "reject_probes": ["looks_like_claude_code"],
        "notes": (
            "accept_names are names Claude Code never sends, claimed before any marker check "
            "-- except against a client_type that names another vendor. PermissionRequest is "
            "not one: Claude Code sends it too (code.claude.com/docs/en/hooks), so it takes the "
            "marker path; prompt_id is required alongside looks_like_claude_code(raw) being false."
        ),
    },
    "kimi_code": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "client_types": ["kimi_code_cli"],
        "accept_any_name": True,
        "notes": (
            "client_type cannot be absent here, so a payload carrying it has positively "
            "self-identified and is claimed whatever event name it names; parse() resolves an "
            "unmapped name to UNKNOWN, which is how Kimi's vendor drift reaches a caller."
        ),
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
    "goose": {
        "mode": "marker",
        "event_key": ["event"],
        "notes": (
            "goose names the event under `event`, a key no other adapter's payload uses (every "
            "other marker family reads hook_event_name or hookEventName), so the event key alone "
            "separates it."
        ),
    },
    "openhands": {
        "mode": "marker",
        "event_key": ["event_type"],
        "notes": (
            "OpenHands names the event under `event_type`, a key no other adapter's payload uses, "
            "so the event key alone separates it (docs.openhands.dev hooks page, read 2026-10-11)."
        ),
    },
    "vscode_copilot": {
        "mode": "marker",
        "event_key": ["hook_event_name", "hookEventName"],
        "accept_markers": ["timestamp"],
        "reject_markers": ["turn_id"],
        "notes": (
            "Accepted five ways (vscode_copilot.py claims()): (1) a name in EVENT_MAP with the "
            "vscode envelope marker timestamp present and turn_id absent -- the only "
            "unconditional reject, captured above; (2) any lowercase-first event name in "
            "EVENT_MAP (Copilot CLI's own camelCase names), unless permission_mode, model, "
            "cursor_version, conversation_id, generation_id or workspace_roots is present -- "
            "these only reject payloads that fall through to path (2), not every payload, so "
            "they are not listed as unconditional reject_markers; (3) a payload naming no "
            "event but carrying toolArgs (Copilot CLI's camelCase input, which has no event "
            "name); (4) a memory-tool call carrying tool_input.command; (5) a payload naming no event "
            "but carrying stopReason (Copilot's camelCase agentStop, live 2026-09-28), parsed as a stop."
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
    behaviour (matrix.json's own row-level verified.basis/date): the config claims above describe
    exactly that behaviour, so inventing a second, unrelated evidence trail for the same facts
    would not be more honest, only duplicated."""
    verified = MATRIX[agent]["verified"]
    return {
        claim: {"basis": verified["basis"], "date": verified["date"], "test": _EVIDENCE_TEST[claim]}
        for claim in _EVIDENCE_CLAIMS
    }
