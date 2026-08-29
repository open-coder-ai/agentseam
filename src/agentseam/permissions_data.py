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

#: Every agent the matrix knows that has no permission model recorded here, and why.
#:
#: The list is exhaustive on purpose, and a test enforces that: recorded plus unrecorded
#: must equal the matrix exactly. An agent simply *missing* from both is the failure this
#: module exists to prevent -- it reads as "nothing to say here" when the truth is "nobody
#: looked". Four agents sat in that state until this table was completed.
#:
#: Note what is deliberately NOT inferred. An agent with no hook surface (Aider, Zed) may
#: still have a permission config; the two are unrelated, and treating "cannot hook" as
#: "cannot restrict" would be a different claim than the one we are entitled to make.
UNRECORDED = {
    "copilot": "a distribution-only identity (the Agent Plugins 1.0 marketplace bundle format, "
    "see packaging_data.PACKAGING), not a live settings surface of its own -- a repo running "
    "an installed copilot-format plugin is running actual GitHub Copilot, whose "
    "auto-approve-map permission model is already recorded under vscode_copilot; duplicating "
    "it here under a second key would claim a second, separate config surface that does not "
    "exist",
    "aider": "no permission model established here. Note this is independent of its lack of "
    "a hook surface: not being able to gate tool calls says nothing about what its config "
    "file can restrict",
    "antigravity": "a permission system provably exists -- its hooks return permissionOverrides, "
    'its decisions respect a user\'s "Always Allow", and it exposes list_permissions and '
    "ask_permission as tools -- but the config schema behind it was not read here",
    "cursor": "its hook surface is now recorded (see the matrix), and hooks are a permission "
    "mechanism -- but the settings-file allow/deny model is a separate thing, and that "
    "documentation was not available here",
    "devin": "a permission system provably exists -- its hooks carry a PermissionRequest event "
    "and the vendor lists modifying permissions as a use case -- but its config was not read here",
    "grok": "a permission system provably exists -- a PermissionDenied hook event fires when it "
    "denies a tool call -- but its config was not read here",
    "junie": "a permission system provably exists -- PermissionRequest is one of its hook "
    "events, and it lists the tool categories the dialog covers -- but the settings that "
    "govern it were not read here",
    "kimi_code": "a permission system provably exists, and its own hooks documentation points at "
    'it as the real barrier ("rely on permission approvals and manual confirmation") -- but '
    "the approval config schema was not read here",
    "replit": "no permission model established here",
    "tabnine": "no permission model established here; vendor documentation is unreachable from this environment",
    "windsurf": "vendor documentation unreachable from the environment this was written in; "
    "no permission model claimed rather than one guessed",
    "zed": "no permission model established here. As with Aider, this is independent of its lack of a hook surface",
}
