"""Renderer data for the config-driven vendors: words, degradation notes, reason defaults.

Split from `tables.py` by activity (the 300-line budget). Like that module's tables these
are stated, not derived, and every value is replayed by the golden wire fixtures.
"""

from __future__ import annotations

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
            "escalate_from_transform": "%s (Devin cannot modify the input at %s, so this is a block)",
        },
        "reason_defaults": {"transform": "input requires modification"},
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
    "goose": {
        "words": {"block": "block"},
        "degrade_notes": {
            "escalate": "goose cannot prompt for confirmation",
            "escalate_from_transform": "goose cannot modify a tool call",
            "transform": "goose cannot modify a tool call",
        },
        "note_style": "because",
    },
    "cursor": {
        "words": {"allow": "allow", "block": "deny", "escalate": "ask"},
        "degrade_notes": {
            "escalate": "%s cannot prompt for confirmation, so this is a block",
            "escalate_from_transform": "%s cannot modify the input, so this is a block",
            "transform": "input requires modification, which this gate cannot express",
            "transform_missing_input": "no replacement input was supplied",
        },
        "flag_note": "observed after the fact (%s cannot prevent it): %s",
        "flag_note_default": "policy violation",
        "default_wire_event": "beforeShellExecution",
        # Witnessed 3.21.18 (2026-09-23): a silent stop hook ended the turn as it would have,
        # and failClosed at stop was not part of the witness, so the gate is never installed
        # fail-closed and its allow stays the silence that was seen.
        "allow_silent_events": ["stop"],
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


def verdict_dialect(agent):
    """The words/notes/defaults block for a config-driven vendor, or {} for the rest."""
    return dict(_VERDICT_DIALECT.get(agent, {}))
