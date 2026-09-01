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
        "accept_names": ["PermissionRequest", "PostCompaction"],
        "reject_probes": ["looks_like_claude_code"],
        "notes": (
            "accept_names are names Claude Code never sends, claimed before any marker check; "
            "prompt_id is required alongside looks_like_claude_code(raw) being false."
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


#: Renderer data for the config-driven hook_json vendors (dialect-families.md §3.1: word
#: tables and degradation-note strings are config, verbatim from the adapters they replaced).
#: Every note/word below is frozen in tests/fixtures/golden/<agent>.json and replayed by
#: test_wire_output_matches_the_frozen_fixture on every run -- a wrong string fails there.
_VERDICT_DIALECT = {
    "claude_code": {
        "words": {"deny": "deny", "escalate": "ask", "transform": "allow", "vouch": "allow", "block": "block"},
        "degrade_notes": {
            "escalate": "confirmation requested; this event cannot prompt, so it blocks",
            "transform": "input rewrite requested; this event cannot modify input, so it blocks",
        },
        "reason_defaults": {"deny_gate": "blocked", "escalate_gate": "confirmation required"},
        "note_style": "suffix",
        "echo": "reverse_map",
        "context_events": ["SessionStart", "UserPromptSubmit"],
        "context_source": "context",
    },
    "codex_cli": {
        "words": {"deny": "deny", "transform": "allow", "block": "block"},
        "degrade_notes": {
            "escalate": "Codex CLI cannot prompt for confirmation at this event",
            "escalate_gate": "Codex CLI does not support ask; asking would fail open",
            "transform": "Codex CLI cannot modify a tool call at this event",
            "transform_missing_input": "Codex CLI cannot apply a rewrite with no updatedInput",
        },
        "reason_defaults": {"deny_gate": "blocked"},
        "note_style": "because",
        "echo": "reverse_map",
    },
    "kimi_code": {
        "words": {"deny": "deny"},
        "degrade_notes": {
            "escalate": "Kimi Code cannot prompt for confirmation",
            "escalate_from_transform": "Kimi Code cannot modify a tool call",
            "transform": "Kimi Code cannot modify a tool call",
        },
        "note_style": "because",
        "echo": "payload",
    },
    "devin": {
        "words": {"allow": "approve", "block": "block"},
        "degrade_notes": {
            "escalate": "Devin cannot prompt for confirmation, so this is a block",
            "escalate_from_transform": "Devin cannot modify a tool call, so this is a block",
        },
        "reason_defaults": {"transform": "input requires modification before it can run"},
        "note_style": "suffix",
        "echo": "payload",
        "default_wire_event": "PreToolUse",
        "context_events": ["PostToolUse", "SessionStart", "UserPromptSubmit"],
        "context_source": "reason",
    },
    "gemini_cli": {
        "words": {"allow": "allow", "block": "deny", "escalate": "ask"},
        "degrade_notes": {"escalate": "%s (confirmation required; %s cannot prompt from a hook)"},
        "reason_defaults": {"escalate": "policy requires confirmation", "escalate_gate": "confirmation required"},
    },
    "junie": {
        "words": {"allow": "allow", "block": "block", "escalate": "ask", "transform": "allow"},
        "degrade_notes": {"transform_missing_input": "no replacement input was supplied"},
        "reason_defaults": {"escalate_gate": "confirmation required", "transform": "input requires modification"},
        "gate_reason_defaults": {"Stop": "not finished"},
        "allow_silent_events": ["Stop"],
        "allow_context_key": "additionalContext",
        "context_source": "reason",
        "note_style": "suffix",
    },
    "tabnine": {
        "words": {"allow": "allow", "block": "deny"},
        "degrade_notes": {
            "escalate": "Tabnine cannot prompt for confirmation",
            "escalate_from_transform": "Tabnine cannot modify a tool call",
            "transform": "Tabnine cannot modify a tool call",
        },
        "note_style": "because",
        "missing_wire": "reverse_map",
    },
    "grok": {
        "words": {"block": "deny"},
        "degrade_notes": {
            "escalate": "Grok cannot prompt for confirmation",
            "escalate_from_transform": "Grok cannot modify a tool call",
            "transform": "Grok cannot modify a tool call",
        },
        "note_style": "because",
    },
    "cursor": {
        "words": {"allow": "allow", "block": "deny", "escalate": "ask"},
        "degrade_notes": {
            "escalate": "%s cannot prompt for confirmation, so this is a block",
            "escalate_from_transform": "%s cannot modify a tool call, so this is a block",
            "transform": "input requires modification, which this gate cannot express",
        },
        "flag_note": "observed after the fact (%s cannot prevent it): %s",
        "flag_note_default": "policy violation",
        "default_wire_event": "beforeShellExecution",
    },
    "windsurf": {
        "degrade_notes": {
            "escalate": "this agent cannot prompt for confirmation; blocking instead",
            "escalate_from_transform": "this agent cannot rewrite tool input; blocking instead",
            "transform": "this agent cannot rewrite tool input; blocking instead",
        },
        "reason_defaults": {"escalate": "confirmation required", "transform": "input requires modification"},
        "note_style": "suffix",
        "flag_note": "windsurf: flagged after the fact (%s cannot block): %s",
        "flag_note_default": "policy violation",
    },
    "antigravity": {
        "words": {"allow": "allow", "block": "deny", "escalate": "ask"},
        "words_at": {"Stop": {"allow": "stop", "block": "continue"}},
        "degrade_notes": {
            "escalate": "Antigravity cannot prompt at Stop",
            "escalate_from_transform": "Antigravity cannot modify a tool call",
            "transform": "Antigravity cannot modify a tool call",
        },
        "reason_defaults": {"escalate": "confirmation required"},
        "gate_reason_defaults": {"Stop": "policy requires more work"},
        "note_style": "because",
        "default_wire_event": "PreToolUse",
    },
}


def family(agent):
    return _FAMILY[agent]


def claims(agent):
    if agent in _SHAPE_INFERRED:
        return {"mode": "shape_inferred"}
    return dict(_CLAIMS[agent])


def verdict_dialect(agent):
    """The words/notes/defaults block for a config-driven vendor, or {} for the rest."""
    return dict(_VERDICT_DIALECT.get(agent, {}))


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
