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
from .matrix_evidence import EVIDENCE
from .matrix_notes import NOTES
from .matrix_terms import (
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
        "verified": EVIDENCE["claude_code"],
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
        "verified": EVIDENCE["cursor"],
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
        "verified": EVIDENCE["kimi_code"],
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
    "junie": {
        "display": "Junie CLI",
        "tier": TIER_FULL,
        "config": "~/.junie/config.json",
        "verified": EVIDENCE["junie"],
        "events": {
            SESSION_START: _cap(),
            SESSION_END: _cap(),
            PROMPT_SUBMIT: _cap(block=True, fail=FAIL_OPEN),
            PRE_TOOL: _cap(block=True, rewrite=True, fail=FAIL_OPEN),
            STOP: _cap(block=True, fail=FAIL_OPEN),
        },
        "notes": NOTES["junie"],
    },
    "tabnine": {
        "display": "Tabnine CLI",
        "tier": TIER_BLOCK,
        "config": ".tabnine/agent/settings.json",
        "verified": EVIDENCE["tabnine"],
        "events": {
            SESSION_START: _cap(),
            SESSION_END: _cap(),
            PROMPT_SUBMIT: _cap(block=True, fail=FAIL_OPEN),
            PRE_TOOL: _cap(block=True, fail=FAIL_OPEN),
            POST_TOOL: _cap(block=True, fail=FAIL_OPEN),
            STOP: _cap(block=True, fail=FAIL_OPEN),
            PRE_COMPACT: _cap(),
        },
        "notes": NOTES["tabnine"],
    },
    "vscode_copilot": {
        "display": "GitHub Copilot (VS Code agent mode / CLI)",
        "tier": TIER_FULL,
        "config": ".github/hooks/*.json",  # also ~/.copilot/hooks/*.json for the CLI
        "verified": EVIDENCE["vscode_copilot"],
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
        "verified": EVIDENCE["grok"],
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
        "verified": EVIDENCE["antigravity"],
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
        "verified": EVIDENCE["gemini_cli"],
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
        "verified": EVIDENCE["codex_cli"],
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
        "verified": EVIDENCE["windsurf"],
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
        "verified": EVIDENCE["devin"],
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
