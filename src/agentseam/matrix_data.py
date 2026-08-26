"""Per-agent capability data. Declaring what an agent can do is a different activity
from answering questions about it, so the table lives here and the queries live in
`matrix.py`. Import from `agentseam.matrix` (or the package root) rather than from here.
"""

from __future__ import annotations

from .contract import (
    FILE_CHANGED,
    INSTRUCTIONS_LOADED,
    POST_TOOL,
    PRE_COMPACT,
    PRE_TOOL,
    PROMPT_SUBMIT,
    SESSION_END,
    SESSION_START,
    STOP,
    SUBAGENT_START,
    SUBAGENT_STOP,
    TOOL_FAILURE,
)
from .matrix_notes import NOTES
from .matrix_terms import (
    BASIS_DOCS,
    BASIS_LIVE,
    BASIS_SOURCE,
    BASIS_THIRD_PARTY,
    FAIL_CLOSED,
    FAIL_CONFIGURABLE,
    FAIL_OPEN,
    TIER_BLOCK,
    TIER_FULL,
    _cap,
)

MATRIX = {
    "claude_code": {
        "display": "Claude Code",
        "tier": TIER_FULL,
        "config": ".claude/settings.json",
        "verified": {
            "basis": BASIS_LIVE,
            "version": "2.1.245",
            "date": "2026-08-25",
            "method": "live headless run + official hooks reference",
        },
        "events": {
            PRE_TOOL: _cap(block=True, rewrite=True, fail=FAIL_CLOSED),
            POST_TOOL: _cap(),
            TOOL_FAILURE: _cap(),
            PROMPT_SUBMIT: _cap(block=True, fail=FAIL_CLOSED),
            SESSION_START: _cap(),
            SESSION_END: _cap(),
            STOP: _cap(block=True),
            PRE_COMPACT: _cap(block=True),
            SUBAGENT_START: _cap(),
            SUBAGENT_STOP: _cap(),
            INSTRUCTIONS_LOADED: _cap(),
            FILE_CHANGED: _cap(),
        },
        "notes": NOTES["claude_code"],
    },
    "cursor": {
        "display": "Cursor",
        "tier": TIER_FULL,
        "config": ".cursor/hooks.json",
        "verified": {
            "basis": BASIS_DOCS,
            "version": "1.7+",
            "date": "2026-08-26",
            "method": "vendor hooks documentation read directly (event list, per-event schemas, exit codes)",
        },
        "events": {
            # preToolUse is generic -- it fires for every tool, not just shell -- and its
            # response carries updated_input, so this is a real block-and-rewrite gate.
            PRE_TOOL: _cap(block=True, rewrite=True, fail=FAIL_CONFIGURABLE),
            POST_TOOL: _cap(),
            TOOL_FAILURE: _cap(),
            PROMPT_SUBMIT: _cap(block=True, fail=FAIL_CONFIGURABLE),
            SESSION_START: _cap(),
            SESSION_END: _cap(),
            SUBAGENT_START: _cap(),
            SUBAGENT_STOP: _cap(),
            STOP: _cap(),
            PRE_COMPACT: _cap(),
            # afterFileEdit lands after the write and supports no output fields at all.
            FILE_CHANGED: _cap(),
        },
        "notes": NOTES["cursor"],
    },
    "kimi_code": {
        "display": "Kimi Code CLI",
        "tier": TIER_BLOCK,
        "config": "config.toml",
        "verified": {
            "basis": BASIS_DOCS,
            "version": "CLI",
            "date": "2026-08-26",
            "method": "vendor hooks documentation read directly (event table, return values, config fields)",
        },
        "events": {
            PRE_TOOL: _cap(block=True, fail=FAIL_OPEN),
            POST_TOOL: _cap(),
            TOOL_FAILURE: _cap(),
            PROMPT_SUBMIT: _cap(block=True, fail=FAIL_OPEN),
            SESSION_START: _cap(),
            SESSION_END: _cap(),
            SUBAGENT_START: _cap(),
            SUBAGENT_STOP: _cap(),
            STOP: _cap(block=True, fail=FAIL_OPEN),
            PRE_COMPACT: _cap(),
        },
        "notes": NOTES["kimi_code"],
    },
    "vscode_copilot": {
        "display": "GitHub Copilot (VS Code agent mode / CLI)",
        "tier": TIER_FULL,
        "config": ".github/hooks/*.json",  # also ~/.copilot/hooks/*.json for the CLI
        "verified": {
            "basis": BASIS_SOURCE,
            "version": "1.110+",
            "date": "2026-08-26",
            "method": "microsoft/vscode source: languageModelToolsService.invokeTool + hookCommandTypes",
        },
        "events": {
            PRE_TOOL: _cap(block=True, rewrite=True, fail=FAIL_CLOSED),
            POST_TOOL: _cap(),
            TOOL_FAILURE: _cap(),
            PROMPT_SUBMIT: _cap(),
            SESSION_START: _cap(),
            SESSION_END: _cap(),
        },
        "notes": NOTES["vscode_copilot"],
    },
    "grok": {
        "display": "Grok CLI",
        "tier": TIER_BLOCK,
        "config": ".grok/hooks/agentseam.json",
        "verified": {
            "basis": BASIS_DOCS,
            "version": "CLI",
            "date": "2026-08-26",
            "method": "vendor hooks documentation read directly (events, script contract, exit codes)",
        },
        "events": {
            PRE_TOOL: _cap(block=True, fail=FAIL_OPEN),
            POST_TOOL: _cap(),
            TOOL_FAILURE: _cap(),
            PROMPT_SUBMIT: _cap(),
            SESSION_START: _cap(),
            SESSION_END: _cap(),
            SUBAGENT_START: _cap(),
            SUBAGENT_STOP: _cap(),
            STOP: _cap(),
            PRE_COMPACT: _cap(),
        },
        "notes": NOTES["grok"],
    },
    "antigravity": {
        "display": "Antigravity",
        "tier": TIER_BLOCK,
        "config": ".agents/hooks.json",
        "verified": {
            "basis": BASIS_DOCS,
            "version": "2.0 / CLI",
            "date": "2026-08-26",
            "method": "vendor hooks documentation read directly (per-event schemas and decision vocabulary)",
        },
        "events": {
            PRE_TOOL: _cap(block=True, fail=FAIL_OPEN),
            POST_TOOL: _cap(),
            STOP: _cap(block=True, fail=FAIL_OPEN),
        },
        "notes": NOTES["antigravity"],
    },
    "gemini_cli": {
        "display": "Gemini CLI",
        "tier": TIER_FULL,
        "config": ".gemini/settings.json",
        "verified": {
            "basis": BASIS_DOCS,
            "version": "docs @ main 2026-08-26",
            "date": "2026-08-26",
            "method": "vendor hooks reference (docs/hooks/reference.md in google-gemini/gemini-cli), read from a clone",
        },
        "events": {
            PRE_TOOL: _cap(block=True, rewrite=True, fail=FAIL_OPEN),
            POST_TOOL: _cap(block=True),
            PROMPT_SUBMIT: _cap(block=True),
            STOP: _cap(block=True),
            SESSION_START: _cap(),
            SESSION_END: _cap(),
            PRE_COMPACT: _cap(),
        },
        "notes": NOTES["gemini_cli"],
    },
    "codex_cli": {
        "display": "OpenAI Codex CLI",
        "tier": TIER_FULL,
        "config": ".codex/hooks.json",
        "verified": {
            "basis": BASIS_SOURCE,
            "version": "source @ main 2026-08-26",
            "date": "2026-08-26",
            "method": "vendor source: codex-rs/hooks/src/schema.rs, engine/output_parser.rs, HookEventName.ts",
        },
        "events": {
            PRE_TOOL: _cap(block=True, rewrite=True, fail=FAIL_OPEN),
            POST_TOOL: _cap(),
            PROMPT_SUBMIT: _cap(block=True),
            SESSION_START: _cap(),
            SESSION_END: _cap(),
            PRE_COMPACT: _cap(),
            STOP: _cap(block=True),
            SUBAGENT_START: _cap(),
            SUBAGENT_STOP: _cap(),
        },
        "notes": NOTES["codex_cli"],
    },
    "windsurf": {
        "display": "Windsurf (Cascade)",
        "tier": TIER_BLOCK,
        "config": ".windsurf/hooks.json",
        "verified": {
            "basis": BASIS_THIRD_PARTY,
            "version": "hooks.json schema as shipped 2026-08",
            "date": "2026-08-26",
            "method": "a real working installation (.windsurf/hooks.json + hook scripts) in "
            "PaloAltoNetworks/prisma-airs-integrations; vendor docs unreachable from this network",
        },
        "events": {
            PROMPT_SUBMIT: _cap(block=True),
            PRE_TOOL: _cap(block=True),
            POST_TOOL: _cap(),
            STOP: _cap(),
        },
        "notes": NOTES["windsurf"],
    },
    "devin": {
        "display": "Devin",
        "tier": TIER_FULL,
        "config": ".devin/hooks.v1.json",
        "verified": {
            "basis": BASIS_DOCS,
            "version": "CLI",
            "date": "2026-08-26",
            "method": "vendor hooks documentation read directly (events, output format, exit codes)",
        },
        "events": {
            PRE_TOOL: _cap(block=True, rewrite=True, fail=FAIL_OPEN),
            POST_TOOL: _cap(),
            PROMPT_SUBMIT: _cap(block=True, fail=FAIL_OPEN),
            SESSION_START: _cap(),
            SESSION_END: _cap(),
            STOP: _cap(block=True, fail=FAIL_OPEN),
            PRE_COMPACT: _cap(),
        },
        "notes": NOTES["devin"],
    },
}


# The gap rows are maintained in their own module but belong to one table: a consumer
# asking about a known agent should get its row, not a KeyError that reads as though the
# agent were unheard of.
from .matrix_gaps import GAPS  # noqa: E402  (below MATRIX so the import resolves)

MATRIX.update(GAPS)
