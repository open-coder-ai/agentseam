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
    "factory_droid": "hook_json",
    "mistral_vibe": "flat_decision",
    "cline": "hook_json",
    "cursor": "cursor",
    "windsurf": "windsurf",
    "antigravity": "antigravity",
}

_SHAPE_INFERRED = frozenset({"cursor", "windsurf", "antigravity"})

_CLAUDE_CODE_CLAIMS_NOTES = (
    "prompt_id rejects only when looks_like_claude_code(raw) is also false; a real Claude Code payload "
    "may carry prompt_id and must still be accepted (matrix-notes.json: fixed 2026-08-27). A value Claude"
    " Code never sends beats every marker key, looks_like_claude_code's included (value-based detection, "
    "D1): permission_mode values off, spec, auto-low, auto-medium and auto-high are Factory Droid's "
    "(docs.factory.com/harness/hooks, read 2026-10-11); tool_name values fs_read, fsRead, fs_write, "
    "fsWrite, execute_bash, execute_cmd and use_aws (kiro.dev/docs/reference/built-in-tools, updated "
    "2026-10-10), and an MCP tool spelled mcp_<server>_<tool> rather than Claude's mcp__<server>__<tool> "
    "(kiro.dev/docs/hooks/types, updated 2026-10-10), are Kiro's. Kiro's V3 primary names (read, write, "
    "shell) and its tool-less events carry nothing Claude Code does not, so those still read as "
    "claude_code. factory_droid claims Droid's payloads on those same permission_mode values "
    "(accept_values, D2a); Kiro has no adapter, so its separable payloads detect as no agent rather "
    "than as claude_code."
)

_GROK_CLAIMS_NOTES = (
    "Grok Build sends hookEventName with grok's snake_case value (pre_tool_use) beside a hook_event_name "
    "key carrying the PascalCase name (github.com/xai-org/grok-build user-guide/10-hooks.md, read "
    "2026-10-11 against v1.0.50), so hook_event_name is read first, but only when event_keys_agree(raw) "
    "finds hookEventName naming the same event (its snake_case twin, or the same text); a payload whose "
    "two keys disagree is not grok's (Kimi Code sends both, with a camelCase hookEventName). The older "
    "camelCase-only shape falls back to hookEventName, which is required either way. Grok Build writes "
    "that twin pair for every event (xai-org/grok-build@2bdd1d6 crates/codegen/xai-grok-hooks/src/event.rs, "
    "to_hook_json), so an event name grok has no mapping for is still claimed when the pair is twins "
    "(event_keys_are_twins) and parses as unknown; the camelCase-only shape carries no such proof."
)

_CLAIMS = {
    "claude_code": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "client_types": [None, "claude_code"],
        "reject_markers": ["turn_id", "project_path", "timestamp"],
        "reject_markers_unless_probe": {"looks_like_claude_code": ["prompt_id"]},
        "reject_probes": ["names_a_single_underscore_mcp_tool"],
        "reject_values": {
            "permission_mode": ["off", "spec", "auto-low", "auto-medium", "auto-high"],
            "tool_name": ["fs_read", "fsRead", "fs_write", "fsWrite", "execute_bash", "execute_cmd", "use_aws"],
        },
        "notes": _CLAUDE_CODE_CLAIMS_NOTES,
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
        # The positive marks of the vendors whose SessionStart/SessionEnd grew a timestamp in the
        # prerelease review (AS-1a) and were claimed here too; the same discipline as VS Code's
        # envelope claim, and the same five Droid values claude_code rejects.
        "reject_markers": [
            "turn_id",
            "project_path",
            "prompt_id",
            "client_type",
            "conversation_id",
            "generation_id",
            "workspace_roots",
            "cursor_version",
        ],
        "reject_values": {"permission_mode": ["off", "spec", "auto-low", "auto-medium", "auto-high"]},
        "notes": (
            "timestamp identifies Tabnine but cannot exclude Gemini CLI, which sends it too "
            "(tabnine.py notes); detect() declines when both could claim, and the agent must "
            "be named explicitly. A positive mark of another vendor beats the shared key: Codex's "
            "turn_id, Junie's project_path, Devin's prompt_id, a client_type, Cursor's base-schema "
            "keys and Droid's permission_mode values are rejected, so a SessionStart or SessionEnd "
            "of theirs that grows a timestamp is not claimed here too (prerelease review, AS-1a)."
        ),
    },
    "grok": {
        "mode": "marker",
        "event_key": ["hook_event_name", "hookEventName"],
        "accept_markers": ["hookEventName"],
        "reject_markers_unless_probe": {"event_keys_agree": ["hook_event_name"]},
        "accept_any_name_when": "event_keys_are_twins",
        "notes": _GROK_CLAIMS_NOTES,
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
    "factory_droid": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "accept_values": {"permission_mode": ["off", "spec", "auto-low", "auto-medium", "auto-high"]},
        "notes": (
            "Droid's payload carries Claude Code's keys, so only a value separates it: every Droid event "
            "carries permission_mode, and Droid sends only off, spec, auto-low, auto-medium or auto-high "
            "there (docs.factory.com/harness/hooks, read 2026-10-11; droid 0.238.0's own hook-input builder "
            "maps every autonomy mode to one of those five, defaulting to off). claude_code rejects exactly "
            "those values (reject_values), so a payload is claimed by one of the two and never by both. A "
            "Droid build that sent a Claude Code permission_mode value would detect as claude_code again, "
            "whose deny Droid also reads."
        ),
    },
    "mistral_vibe": {
        "mode": "marker",
        "event_key": ["hook_event_name"],
        "notes": (
            "Vibe names the event under hook_event_name with its own snake_case hook types (pre_tool, "
            "post_tool, post_agent), which no other adapter maps, so the event name alone separates it "
            "(docs.mistral.ai/vibe/code/cli/hooks and vibe/core/hooks/models.py HookType at mistral-vibe "
            "2.26.1, read 2026-10-11)."
        ),
    },
    "cline": {
        "mode": "marker",
        "event_key": ["hookName"],
        "accept_markers": ["clineVersion"],
        "notes": (
            "Every Cline hook payload carries clineVersion beside hookName (.clinerules/hooks/README.md in "
            "cline/cline, read 2026-10-11; the SDK's createPayloadBase sets it on every event, empty when "
            "CLINE_VERSION is unset). No other vendor sends either key, so the claim is a marker one. "
            "hookName is the documented file name (PreToolUse) from the VS Code extension and the SDK's own "
            "event name (tool_call) from the CLI; both are mapped."
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


#: Where a shape-inferred vendor does name its event. windsurf: docs.devin.ai/desktop/
#: cascade/hooks (read 2026-10-13), the common input's "agent_action_name | string | The
#: hook event name"; hook_event_name is what the 2026-08-26 third-party install sent.
_SHAPE_EVENT_KEYS = {"windsurf": ["agent_action_name", "hook_event_name"]}


def claims(agent):
    if agent in _SHAPE_INFERRED:
        out = {"mode": "shape_inferred"}
        if agent in _SHAPE_EVENT_KEYS:
            out["event_key"] = list(_SHAPE_EVENT_KEYS[agent])
        return out
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
