"""Primitive 3 data: how each agent packages reusable parts, and where it looks for them.

The surprise here is how much already lines up. A Claude Code plugin and a Gemini CLI
extension are, underneath two different manifests, close to the same directory:

    skills/<name>/SKILL.md      identical
    agents/<name>.md            identical
    hooks/hooks.json            identical
    commands/<name>.{md,toml}   same folder, different file format

So one directory can serve both, and the only real work is writing the second manifest and
the commands twice. VS Code goes further and reads several of Claude Code's own folders --
`.claude/skills`, `.claude/agents`, `.claude/rules`, and hooks straight out of
`.claude/settings.json` -- which is recorded in ALSO_READS because it means a repository
often already ships parts to an agent nobody wired it to.

`parts` maps a canonical part to a path template, or to None where the agent has no
equivalent. As everywhere else here, None is a claim, not an oversight.
"""

from __future__ import annotations

# --- canonical parts of a bundle ------------------------------------------------
SKILL = "skill"  # a capability folder the agent loads on demand
SUBAGENT = "subagent"  # a delegated persona
COMMAND = "command"  # a user-invoked prompt, /like-this
HOOKS = "hooks"  # lifecycle hook config (primitive 1's install target)
MCP = "mcp"  # MCP server declarations
PARTS = (SKILL, SUBAGENT, COMMAND, HOOKS, MCP)

#: The neutral namespace. `.agents/skills` is to packaging what AGENTS.md is to
#: instructions: a vendor-independent location more than one agent already reads.
SHARED_SKILL_DIR = ".agents/skills"

PACKAGING = {
    "claude_code": {
        "unit": "plugin",
        "manifest": ".claude-plugin/plugin.json",
        "manifest_format": "json",
        "project_root": ".claude",
        "parts": {
            SKILL: "skills/{name}/SKILL.md",
            SUBAGENT: "agents/{name}.md",
            COMMAND: "commands/{name}.md",
            HOOKS: "hooks/hooks.json",
            MCP: ".mcp.json",
        },
        "notes": (
            "Only plugin.json lives inside .claude-plugin/; every component directory sits "
            "at the plugin root. Outside a plugin the same parts live under .claude/ in a "
            "repository, which is why VS Code can read them without Claude Code installed."
        ),
        "verified": {
            "method": "vendor plugin reference read directly (directory layout and extension table)",
            "date": "2026-08-26",
        },
    },
    "gemini_cli": {
        "unit": "extension",
        "manifest": "gemini-extension.json",
        "manifest_format": "json",
        "project_root": ".gemini/extensions/{bundle}",
        "parts": {
            SKILL: "skills/{name}/SKILL.md",
            SUBAGENT: "agents/{name}.md",
            COMMAND: "commands/{name}.toml",
            HOOKS: "hooks/hooks.json",
            MCP: None,
        },
        "notes": (
            "Commands are TOML with a required `prompt` field and an optional `description`; "
            "a nested commands/gcs/sync.toml becomes /gcs:sync. Hooks are deliberately not "
            "declared in the manifest -- hooks/hooks.json is found by location, exactly as in "
            "a Claude Code plugin. MCP servers have no file of their own: they are declared "
            "inside gemini-extension.json, so a rendered .mcp.json would be ignored."
        ),
        "verified": {
            "method": "source read: docs/extensions/reference.md, docs/cli/custom-commands.md",
            "date": "2026-08-26",
        },
    },
    "vscode_copilot": {
        # No bundle format: parts are found by location, so there is nothing to install
        # and nothing to name. That is a real difference, not a missing feature.
        "unit": None,
        "manifest": None,
        "manifest_format": None,
        # Repo root, because the part paths below are already repo-relative: with no bundle
        # there is nothing to nest them inside.
        "project_root": ".",
        "parts": {
            SKILL: ".github/skills/{name}/SKILL.md",
            SUBAGENT: ".github/agents/{name}.agent.md",
            COMMAND: ".github/prompts/{name}.prompt.md",
            HOOKS: ".github/hooks/hooks.json",
            MCP: None,
        },
        "notes": (
            "Parts are loaded from fixed folders rather than a bundle, so there is no manifest "
            "and no install step -- committing the file is the install. Note the doubled "
            "extensions: a subagent is <name>.agent.md and a command is <name>.prompt.md, "
            "where both of the other two use a bare .md."
        ),
        "verified": {
            "method": "source read: src/vs/workbench/contrib/chat/common/promptSyntax/config/promptFileLocations.ts",
            "date": "2026-08-26",
        },
    },
}

#: Why a specific agent cannot hold a specific part. Without these the generic message
#: ("this format has no place for it") would understate Gemini, which supports MCP servers
#: perfectly well -- just in the manifest rather than in a file of its own.
PART_LIMITS = {
    ("gemini_cli", MCP): "MCP servers are declared inside gemini-extension.json, not in a file "
    "of their own; a rendered .mcp.json would simply be ignored",
    ("vscode_copilot", MCP): "MCP servers are configured by the editor rather than shipped alongside these parts",
}

#: Folders an agent reads that belong to *another* agent. This is the interop surface:
#: a repository that ships .claude/skills is already shipping skills to VS Code.
ALSO_READS = {
    "vscode_copilot": {
        SKILL: (SHARED_SKILL_DIR, ".claude/skills", "~/.agents/skills", "~/.copilot/skills", "~/.claude/skills"),
        SUBAGENT: (".claude/agents", "~/.copilot/agents", "~/.claude/agents"),
        HOOKS: (".claude/settings.json", ".claude/settings.local.json", "~/.claude/settings.json"),
    },
}

#: Every agent the matrix knows that has no packaging format recorded here, and why.
#:
#: Exhaustive on purpose, and enforced by a test: recorded plus unrecorded must equal the
#: matrix exactly. A missing agent reads as "nothing to package here" when the truth is
#: "nobody looked", and that is the one thing this module must never say by accident.
#:
#: Several of these are *not* blanks. Where a vendor's own hook documentation proves that
#: skills or subagents exist -- a SubagentStop event, a define_subagent tool, a loader that
#: mentions skills -- that is recorded, because "we could not find the layout" and "there is
#: no such thing" are different answers and only one of them is true.
UNRECORDED = {
    "aider": "no packaging format established here",
    "antigravity": "subagents provably exist -- define_subagent and invoke_subagent are tools it "
    "offers, and its file reader takes an IsSkillFile argument -- but the on-disk layout was "
    "not established here",
    "codex_cli": "skills exist -- the approval config gates skill script execution -- but the "
    "layout documentation redirects to a host this environment's egress policy blocks",
    "cursor": "plugins exist -- hooks can be installed through them, and workspaceOpen "
    "returns pluginPaths for the workspace -- but the directory layout was not established "
    "here, so there is nothing to render",
    "devin": "skills provably exist -- its hook loader is documented as following the same "
    "discovery rules as skills and rules -- but their layout was not read here",
    "grok": "subagents provably exist (SubagentStart and SubagentStop hook events), and it has an "
    "extensions system, but neither layout was established here",
    "junie": "no packaging format established here",
    "kimi_code": "subagents provably exist (a SubagentStop hook event, and a documented agents "
    "and sub-agents feature) but their layout was not read here",
    "replit": "no packaging format established here",
    "tabnine": "no packaging format established here; vendor documentation is unreachable from this environment",
    "windsurf": "vendor documentation unreachable from the environment this was written in",
    "zed": "no packaging format established here",
}
