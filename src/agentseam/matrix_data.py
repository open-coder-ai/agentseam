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
#: The agent fails open by default but can be told to fail closed per hook (Cursor's
#: `failClosed: true`). Neither existing value tells the truth about that: "open" would
#: understate a surface a user can make airtight, and "closed" would claim a default that
#: is not there. What a consumer may claim depends on how the hook was installed.
FAIL_CONFIGURABLE = "configurable"

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
        "tier": TIER_FULL,
        "config": ".cursor/hooks.json",
        "verified": {
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
        "notes": "Fails OPEN by default; failClosed:true per hook definition makes it fail "
        "closed, and agentseam sets it on every gate it installs. `ask` is accepted by the "
        "preToolUse schema but not enforced today, so the adapter denies instead of "
        "returning a prompt that would behave as a pass; beforeShellExecution and "
        "beforeMCPExecution do honour ask. Separate Tab hooks (beforeTabFileRead, "
        "afterTabFileEdit) gate inline completions, and workspaceOpen fires outside any "
        "session with no canonical event here. Cursor also loads Claude Code-format hooks.",
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
    "devin": {
        "display": "Devin",
        "tier": TIER_FULL,
        "config": ".devin/hooks.v1.json",
        "verified": {
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
        "notes": "Speaks Claude Code's hook format almost exactly, and reads .claude/"
        "settings.json for hooks by default -- so a repo with Claude Code hooks is already "
        'running them under Devin. A block is top-level {"decision": "block"}, not '
        "permissionDecision. There is no ask in the vocabulary. Non-zero exit codes other "
        "than 2 are logged without blocking, so this fails OPEN. A SessionStart payload is "
        "indistinguishable from Claude Code's, and detect() refuses to guess between them.",
    },
}


# The gap rows are maintained in their own module but belong to one table: a consumer
# asking about a known agent should get its row, not a KeyError that reads as though the
# agent were unheard of.
from .matrix_gaps import GAPS  # noqa: E402  (below MATRIX so the import resolves)

MATRIX.update(GAPS)
