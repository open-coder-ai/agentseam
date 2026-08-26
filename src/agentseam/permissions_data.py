"""Primitive 4 data: where each agent keeps its permission config, and what that config can say.

Two tables, and the second one is the point.

`CONFIG_FILES` is the boring half: the files, in the order the agent resolves them.
`CAPABILITY` is the half that stops a policy from being a lie -- for each agent it records
*which of allow/ask/deny that agent's config can actually express*, and under which key.
A `None` there means the agent has no way to say it, and a rule asking for it must be
reported back to the caller rather than rendered into something weaker that looks similar.

That distinction is not academic. VS Code's terminal auto-approve map takes `false` for a
pattern, which reads like a denylist and is not one: `false` withholds auto-approval, so the
command still runs once a human clicks through. Writing a "deny" there would hand someone a
guardrail that never blocks anything.

Every row carries `verified`, naming what was actually read. Rows whose source could not be
reached from here say so and claim nothing.
"""

from __future__ import annotations

# --- what a rule can ask for ----------------------------------------------------
ALLOW = "allow"
ASK = "ask"
DENY = "deny"
ACTIONS = (ALLOW, ASK, DENY)

# --- what a rule can be about ---------------------------------------------------
# Deliberately *capabilities*, not tool names. "Bash", "run_shell_command" and
# "runInTerminal" are three vendors' spellings of one idea; a policy should be written
# once against the idea and spelled by the adapter.
SHELL = "shell"
FILE_READ = "file_read"
FILE_WRITE = "file_write"
NETWORK_FETCH = "network_fetch"
MCP = "mcp"
CAPABILITIES = (SHELL, FILE_READ, FILE_WRITE, NETWORK_FETCH, MCP)

# --- config scopes, highest precedence first where an agent has several ----------
MANAGED = "managed"
LOCAL = "local"
PROJECT = "project"
USER = "user"

CONFIG_FILES = {
    "claude_code": [
        {"scope": MANAGED, "path": "managed-settings.json", "format": "json"},
        {"scope": LOCAL, "path": ".claude/settings.local.json", "format": "json"},
        {"scope": PROJECT, "path": ".claude/settings.json", "format": "json"},
        {"scope": USER, "path": "~/.claude/settings.json", "format": "json"},
    ],
    "gemini_cli": [
        {"scope": PROJECT, "path": ".gemini/settings.json", "format": "json"},
        {"scope": USER, "path": "~/.gemini/settings.json", "format": "json"},
    ],
    "codex_cli": [
        {"scope": USER, "path": "~/.codex/config.toml", "format": "toml"},
    ],
    "vscode_copilot": [
        {"scope": PROJECT, "path": ".vscode/settings.json", "format": "json"},
    ],
}

CAPABILITY = {
    "claude_code": {
        "shape": "ordered-rules",
        "actions": {
            ALLOW: "permissions.allow",
            ASK: "permissions.ask",
            DENY: "permissions.deny",
        },
        "deny_authoritative": True,
        "sandbox": None,
        "tools": {
            SHELL: ("Bash",),
            FILE_READ: ("Read",),
            FILE_WRITE: ("Edit", "Write"),
            NETWORK_FETCH: ("WebFetch",),
            MCP: ("mcp__*",),
        },
        "notes": (
            "Rules are evaluated deny, then ask, then allow; the first match wins and "
            "specificity does not reorder them, so a deny rule cannot carry allowlist "
            "exceptions. Denial is authoritative across scopes: a tool denied at any "
            "level cannot be re-allowed at another. allow rules in a committed "
            ".claude/settings.json wait on the workspace trust dialog; deny and ask do "
            "not, since they only restrict. A PreToolUse hook exiting 2 stops the call "
            "before rules are evaluated, and deny/ask rules still apply even when a hook "
            "returns allow -- so hooks and permissions each get the last word on the "
            "outcome they are stricter about."
        ),
        "verified": {
            "method": "vendor documentation read directly (permissions and settings pages)",
            "date": "2026-08-26",
        },
    },
    "gemini_cli": {
        "shape": "tool-allowlist",
        "actions": {
            ALLOW: "tools.allowed",
            ASK: "tools.confirmationRequired",
            DENY: "tools.exclude",
        },
        "deny_authoritative": True,
        "sandbox": "tools.sandboxAllowedPaths / tools.sandboxNetworkAccess",
        "tools": {
            SHELL: ("run_shell_command",),
            FILE_READ: ("read_file",),
            FILE_WRITE: ("write_file", "replace"),
            NETWORK_FETCH: ("web_fetch",),
            MCP: (),
        },
        "notes": (
            "tools.exclude removes a tool from discovery entirely, and its scopes merge by "
            "union -- so an exclusion set in one settings file cannot be dropped by another. "
            "That makes it a real deny, with one sharp edge: it excludes by *tool name*, so "
            "there is no way to exclude only some invocations of a tool. A deny that carries "
            "a specifier has no expression here and is reported as such. "
            "tools.confirmationRequired takes precedence over tools.allowed and tools.core."
        ),
        "verified": {
            "method": "source read: packages/cli/src/config/settingsSchema.ts, docs/cli/settings.md",
            "date": "2026-08-26",
        },
    },
    "codex_cli": {
        "shape": "sandbox+execpolicy",
        "actions": {
            ALLOW: 'prefix_rule(decision="allow")',
            ASK: 'prefix_rule(decision="prompt")',
            DENY: 'prefix_rule(decision="forbidden")',
        },
        # The vocabulary is source-verified; whether "forbidden" survives every approval
        # and sandbox combination was not established here, so this stays unanswered.
        "deny_authoritative": None,
        "sandbox": "sandbox_mode (read-only | workspace-write | danger-full-access | external-sandbox)",
        "tools": {
            SHELL: ("prefix_rule",),
            FILE_READ: (),
            FILE_WRITE: (),
            NETWORK_FETCH: (),
            MCP: (),
        },
        "notes": (
            "Permissions here are two separate mechanisms. approval_policy (untrusted | "
            "on-request | granular | never) and sandbox_mode decide the session's posture; "
            "note that on-failure is now an alias of on-request rather than a mode of its "
            "own. Per-command rules live in a separate Starlark policy file as "
            "prefix_rule(pattern=[...], decision=allow|prompt|forbidden), matching ordered "
            "command tokens. Because the rule language matches command prefixes, only shell "
            "rules can be expressed -- a rule about file writes or fetches has nowhere to go."
        ),
        "verified": {
            "method": "source read: codex-rs/protocol/src/protocol.rs (AskForApproval, SandboxPolicy), "
            "codex-rs/execpolicy/README.md",
            "date": "2026-08-26",
        },
    },
    "vscode_copilot": {
        "shape": "auto-approve-map",
        "actions": {
            ALLOW: "chat.tools.terminal.autoApprove",
            ASK: "chat.tools.terminal.autoApprove",
            DENY: None,
        },
        "deny_authoritative": False,
        "sandbox": "chat.agent.sandbox.fileSystem.{linux,mac,windows} (allowRead/denyRead/allowWrite/denyWrite)",
        "tools": {
            SHELL: ("chat.tools.terminal.autoApprove",),
            FILE_READ: (),
            FILE_WRITE: (),
            NETWORK_FETCH: (),
            MCP: (),
        },
        "notes": (
            "The auto-approve map is {pattern: bool}, where a pattern wrapped in / is a "
            "regular expression. true auto-approves; false only withholds auto-approval and "
            "still lets a human approve the command, so false is not a block and no deny "
            "rule is rendered from it. The older github.copilot.chat.agent.terminal.allowList "
            "and .denyList keys are deprecated in favour of this map, and .denyList never "
            "blocked either. A genuine deny does exist, but for filesystem paths rather than "
            "commands: the agent sandbox settings take denyRead/denyWrite path lists, where "
            "allowRead overrides denyRead and denyWrite overrides allowWrite."
        ),
        "verified": {
            "method": "source read: src/vs/workbench/contrib/terminalContrib/chatAgentTools/common/"
            "terminalChatAgentToolsConfiguration.ts",
            "date": "2026-08-26",
        },
    },
}

#: Agents with a hook adapter but no permission model recorded here. Naming them is the
#: point: silence would read as "no permission surface exists", which is a claim we have
#: not earned. Both vendors publish docs this environment's egress policy blocks.
UNRECORDED = {
    "cursor": "vendor documentation unreachable from the environment this was written in; "
    "no permission model claimed rather than one guessed",
    "windsurf": "vendor documentation unreachable from the environment this was written in; "
    "no permission model claimed rather than one guessed",
}
