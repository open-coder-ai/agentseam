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

# fail_mode: what the AGENT does when the hook crashes/times out.
#   "closed" -> the action is blocked (safe)
#   "open"   -> the action proceeds (a policy claiming enforcement here is overclaiming)
FAIL_CLOSED = "closed"
FAIL_OPEN = "open"

# tier: how much of the surface the adapter can serve.
TIER_FULL = "block+rewrite"
TIER_BLOCK = "block"
TIER_OBSERVE = "observe"
TIER_NONE = "none"
#: Known agent, no hook adapter in agentseam. Distinct from TIER_NONE, which is a claim
#: about the AGENT (it exposes nothing to hook). This one is a claim about US, and it
#: matters: a user can still push instruction files to these agents, they just cannot
#: gate tool calls here yet. Collapsing the two would either slander the agent or
#: overstate our coverage.
TIER_UNADAPTED = "unadapted"


def _cap(block=False, rewrite=False, fail=FAIL_OPEN):
    return {"block": block, "rewrite": rewrite, "fail_mode": fail}


MATRIX = {
    "claude_code": {
        "display": "Claude Code",
        "tier": TIER_FULL,
        "config": ".claude/settings.json",
        "verified": {
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
        "notes": "Richest surface (~30 events). Blocks via exit 2 or "
        "hookSpecificOutput.permissionDecision; rewrite via updatedInput (pre_tool only).",
    },
    "cursor": {
        "display": "Cursor",
        "tier": TIER_BLOCK,
        "config": ".cursor/hooks.json",
        "verified": {
            "version": "1.7+",
            "date": "2026-08-25",
            "method": "official hook examples repo (scripts + test fixtures)",
        },
        "events": {
            # beforeShellExecution / beforeMCPExecution: true pre-execution block.
            PRE_TOOL: _cap(block=True, fail=FAIL_OPEN),
            # afterFileEdit fires AFTER the write lands: detect, never prevent.
            POST_TOOL: _cap(),
            PROMPT_SUBMIT: _cap(),
            SESSION_START: _cap(),
            STOP: _cap(),
            PRE_COMPACT: _cap(),
        },
        "notes": "Fail-OPEN by default (set failClosed:true per hook). No beforeFileEdit: "
        "file writes are audit-only; only shell/MCP calls gate pre-execution.",
    },
    "vscode_copilot": {
        "display": "GitHub Copilot (VS Code agent mode / CLI)",
        "tier": TIER_FULL,
        "config": ".github/hooks/*.json",  # also ~/.copilot/hooks/*.json for the CLI
        "verified": {
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
        "notes": "Same PreToolUse contract as Claude Code (permissionDecision/updatedInput) and "
        "parses Claude settings.json via hookClaudeCompat. Memory writes arrive as the "
        "'memory' tool (create/str_replace/insert), not file edits.",
    },
    "gemini_cli": {
        "display": "Gemini CLI",
        "tier": TIER_FULL,
        "config": ".gemini/settings.json",
        "verified": {
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
        "notes": "Top-level `decision: allow|deny` + `reason` (not nested); rewrite merges via "
        "hookSpecificOutput.tool_input; exit 2 also blocks. Write tools are write_file/replace. "
        "Fail mode is not documented as closed, so pre_tool is rated best-effort rather than enforced.",
    },
    "codex_cli": {
        "display": "OpenAI Codex CLI",
        "tier": TIER_FULL,
        "config": ".codex/hooks.json",
        "verified": {
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
        "notes": "Claude-family decision shape (hookSpecificOutput.permissionDecision) but camelCase "
        "event names and extra turn-scoped fields (turn_id, model, permission_mode). Deny is "
        "sent as JSON with exit 0: on Windows Codex wraps hooks in powershell -Command, which "
        "collapses exit 2 into 1, so an exit-code deny does not survive that platform.",
    },
    "windsurf": {
        "display": "Windsurf (Cascade)",
        "tier": TIER_BLOCK,
        "config": ".windsurf/hooks.json",
        "verified": {
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
        "notes": "Exit code 2 is the ONLY block signal: no stdout decision protocol, no machine-readable "
        "reason, no rewrite. Critically there is NO file-write event -- prompt, terminal and MCP "
        "hooks only -- so a write to a memory file is invisible to a hook on this agent. "
        "Fail mode is undocumented, so blocking rates best-effort rather than enforced.",
    },
    # --- known agents with no hook adapter here (instruction files still work) -----
    # Support level taken from the sibling project's shipped surface matrix, which gives
    # these agents ambient-rule/git/CI surfaces only -- no pre-tool-use hook. Recorded as
    # unadapted rather than none because that is a statement about agentseam, and none of
    # these was independently re-checked for a hook surface here.
    "devin": {
        "display": "Devin",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": {
            "version": "n/a",
            "date": "2026-08-26",
            "method": "sibling project's shipped surface matrix (no pre-tool-use surface); not re-verified here",
        },
        "events": {},
        "notes": "No hook adapter in agentseam. Instruction files are supported "
        "(see agentseam.instructions); tool calls cannot be gated here yet.",
    },
    "grok": {
        "display": "Grok",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": {
            "version": "n/a",
            "date": "2026-08-26",
            "method": "sibling project's shipped surface matrix (no pre-tool-use surface); not re-verified here",
        },
        "events": {},
        "notes": "No hook adapter in agentseam. Instruction files are supported "
        "(see agentseam.instructions); tool calls cannot be gated here yet.",
    },
    "kimi_code": {
        "display": "Kimi Code",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": {
            "version": "n/a",
            "date": "2026-08-26",
            "method": "sibling project's shipped surface matrix (no pre-tool-use surface); not re-verified here",
        },
        "events": {},
        "notes": "No hook adapter in agentseam. Instruction files are supported "
        "(see agentseam.instructions); tool calls cannot be gated here yet.",
    },
    "replit": {
        "display": "Replit",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": {
            "version": "n/a",
            "date": "2026-08-26",
            "method": "sibling project's shipped surface matrix (no pre-tool-use surface); not re-verified here",
        },
        "events": {},
        "notes": "No hook adapter in agentseam. Instruction files are supported "
        "(see agentseam.instructions); tool calls cannot be gated here yet.",
    },
    "tabnine": {
        "display": "Tabnine",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": {
            "version": "n/a",
            "date": "2026-08-26",
            "method": "sibling project's shipped surface matrix (no pre-tool-use surface); not re-verified here",
        },
        "events": {},
        "notes": "No hook adapter in agentseam. Instruction files are supported "
        "(see agentseam.instructions); tool calls cannot be gated here yet.",
    },
    "antigravity": {
        "display": "Antigravity",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": {
            "version": "n/a",
            "date": "2026-08-26",
            "method": "sibling project's shipped surface matrix (no pre-tool-use surface); not re-verified here",
        },
        "events": {},
        "notes": "No hook adapter in agentseam. Instruction files are supported "
        "(see agentseam.instructions); tool calls cannot be gated here yet.",
    },
    "junie": {
        "display": "JetBrains Junie",
        "tier": TIER_UNADAPTED,
        "config": None,
        "verified": {
            "version": "n/a",
            "date": "2026-08-26",
            "method": "not yet researched from a primary source here; a Junie CLI hook surface is reported but unverified",
        },
        "events": {},
        "notes": "No hook adapter in agentseam. Instruction files are supported "
        "(see agentseam.instructions); tool calls cannot be gated here yet.",
    },
    # --- honest floor: agents with no usable hook surface -----------------------
    "zed": {
        "display": "Zed",
        "tier": TIER_NONE,
        "config": None,
        "verified": {"version": "2026-08", "date": "2026-08-26", "method": "docs + open extensibility issues"},
        "events": {},
        "notes": "No user hooks. Only declarative agent.tool_permissions rules. "
        "No deny path for an external handler — say so rather than stretch.",
    },
    "aider": {
        "display": "Aider",
        "tier": TIER_NONE,
        "config": None,
        "verified": {"version": "2026-08", "date": "2026-08-26", "method": "docs/config reference"},
        "events": {},
        "notes": "No lifecycle hooks. Only --lint-cmd/--test-cmd post-edit steps. "
        "Observation possible via git hooks; no interception.",
    },
}
