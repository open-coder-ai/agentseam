"""Primitive 3 data: how each agent packages reusable parts, and where it looks for them."""

from __future__ import annotations

SKILL = "skill"
SUBAGENT = "subagent"
COMMAND = "command"
HOOKS = "hooks"
MCP = "mcp"
EXECUTABLE = "executable"
PARTS = (SKILL, SUBAGENT, COMMAND, HOOKS, MCP, EXECUTABLE)

SHARED_SKILL_DIR = ".agents/skills"

#: **${CODEX_PLUGIN_ROOT} is a trap.** It appears in Codex's own TUI hook browser as sample

PACKAGING = {
    "claude_code": {
        "unit": "plugin",
        "manifest": ".claude-plugin/plugin.json",
        "manifest_format": "json",
        "project_root": ".claude",
        "plugin_root": ("${CLAUDE_PLUGIN_ROOT}",),
        "parts": {
            SKILL: "skills/{name}/SKILL.md",
            SUBAGENT: "agents/{name}.md",
            COMMAND: "commands/{name}.md",
            HOOKS: "hooks/hooks.json",
            MCP: ".mcp.json",
            EXECUTABLE: "scripts/{name}",
        },
        "notes": (
            "Only plugin.json lives inside .claude-plugin/; every component directory sits "
            "at the plugin root. Outside a plugin the same parts live under .claude/ in a "
            "repository, which is why VS Code can read them without Claude Code installed. "
            "scripts/ is the vendor's own documented home for a hook's executable, e.g. "
            "hooks/hooks.json pointing a command at "
            "${CLAUDE_PLUGIN_ROOT}/scripts/format-and-lint.sh, chmod +x'd before packaging."
        ),
        "verified": {
            "method": "vendor plugin reference (directory layout, extension table); scripts/ "
            "confirmed via the plugin-dev skill's hook-development example (${CLAUDE_PLUGIN_ROOT}"
            "/scripts/format-and-lint.sh, chmod +x)",
            "date": "2026-08-29",
        },
    },
    "gemini_cli": {
        "unit": "extension",
        "manifest": "gemini-extension.json",
        "manifest_format": "json",
        "project_root": ".gemini/extensions/{bundle}",
        "plugin_root": ("${extensionPath}",),
        "parts": {
            SKILL: "skills/{name}/SKILL.md",
            SUBAGENT: "agents/{name}.md",
            COMMAND: "commands/{name}.toml",
            HOOKS: "hooks/hooks.json",
            MCP: None,
            EXECUTABLE: "scripts/{name}",
        },
        "notes": (
            "Commands are TOML with a required `prompt` field and an optional `description`; "
            "a nested commands/gcs/sync.toml becomes /gcs:sync. Hooks are deliberately not "
            "declared in the manifest -- hooks/hooks.json is found by location, exactly as in "
            "a Claude Code plugin. MCP servers have no file of their own: they are declared "
            "inside gemini-extension.json, so a rendered .mcp.json would be ignored. "
            "Executable placement has no vendor-reserved folder -- reference.md leaves naming "
            "to the extension developer -- so scripts/ is kept for consistency with the layout "
            "above; a hook command reaches it via ${extensionPath}, confirmed to substitute "
            "inside hooks/hooks.json too, not only the manifest."
        ),
        "verified": {
            "method": "source read: docs/extensions/reference.md, docs/cli/custom-commands.md; "
            "${extensionPath} confirmed by direct quote (fetched 2026-08-29): 'you should use "
            "${extensionPath} to refer to files within your extension directory', substitution "
            "documented for both gemini-extension.json and hooks/hooks.json",
            "date": "2026-08-29",
        },
    },
    "codex_cli": {
        "unit": "plugin",
        "manifest": ".codex-plugin/plugin.json",
        "manifest_format": "json",
        "project_root": "{bundle}",
        "plugin_root": ("${PLUGIN_ROOT}", "${CLAUDE_PLUGIN_ROOT}"),
        "parts": {
            SKILL: "skills/{name}/SKILL.md",
            SUBAGENT: None,
            COMMAND: None,
            HOOKS: "hooks/hooks.json",
            MCP: None,
            EXECUTABLE: None,
        },
        "declares": {SKILL: ("skills", "./skills"), HOOKS: ("hooks", "./hooks/hooks.json")},
        "notes": (
            "Two formats exist and only one carries hooks. `.codex-plugin/plugin.json` is the "
            "Legacy format; a manifest in Agent Plugins 1.0 format is loaded as "
            "PluginManifestFormat::AgentPlugin, and loader.rs then discards its hooks "
            "outright -- `if loaded_manifest.format == PluginManifestFormat::AgentPlugin "
            "{ (Vec::new(), Vec::new()) }`. So shipping the Copilot package to Codex installs "
            "a plugin whose enforcement is deleted at load time while its description still "
            "claims it. Component paths are declared in the manifest and must use the `./...` "
            "syntax the loader validates. `mcp_servers` and `apps` are manifest fields too, "
            "and commands are read from a `commands` field on the same file."
        ),
        "verified": {
            "method": "vendor source read from a clone: codex-rs/core-plugins/src/manifest.rs "
            "(RawPluginManifest fields, the .codex-plugin/plugin.json path, Legacy vs "
            "AgentPlugin formats) and core-plugins/src/loader.rs (hook-discard branch); the "
            "manifest's exhaustive field list (name, version, description, keywords, skills, "
            "mcp_servers, apps, hooks, interface) and plugin-json-spec.md confirm no field "
            "exists for a bundled executable/scripts path",
            "date": "2026-08-29",
        },
    },
    "cursor": {
        "unit": "plugin",
        "manifest": ".cursor-plugin/plugin.json",
        "manifest_format": "json",
        "project_root": "{bundle}",
        "plugin_root": ("${CURSOR_PLUGIN_ROOT}",),
        "parts": {
            SKILL: "skills/{name}/SKILL.md",
            SUBAGENT: None,
            COMMAND: None,
            HOOKS: "hooks/hooks.json",
            MCP: None,
            EXECUTABLE: None,
        },
        "declares": {SKILL: ("skills", "./skills/"), HOOKS: ("hooks", "./hooks/hooks.json")},
        "notes": (
            "Cursor ignores Agent Plugins 1.0 hooks entirely, so neither the Claude nor the "
            "Copilot package reaches its hook engine -- this format is the only one that does. "
            "Like Codex it declares component paths in the manifest rather than finding them "
            "by location. The hooks file is Cursor's own envelope (a `version` stamp and FLAT "
            "entries, no per-entry `hooks` array and no `type`), which is what `install()` "
            "already writes into .cursor/hooks.json, so a plugin install and a repo install "
            "run the identical hook."
        ),
        "verified": {
            "method": "vendor plugin docs, plus the layout as implemented and shipped by a "
            "sibling policy engine's own .cursor-plugin emitter. Cursor is closed source, so "
            "this is the strongest basis available -- weaker than the Codex row beside it, "
            "read from the vendor's own loader. No executable/scripts location was found in "
            "cursor/plugins' own README (layout: .cursor-plugin/, skills/, rules/, mcp.json), "
            "so none is claimed.",
            "date": "2026-08-29",
        },
    },
    "vscode_copilot": {
        "unit": None,
        "manifest": None,
        "manifest_format": None,
        "project_root": ".",
        "plugin_root": ("${PLUGIN_ROOT}", "${CLAUDE_PLUGIN_ROOT}"),
        "parts": {
            SKILL: ".github/skills/{name}/SKILL.md",
            SUBAGENT: ".github/agents/{name}.agent.md",
            COMMAND: ".github/prompts/{name}.prompt.md",
            HOOKS: ".github/hooks/hooks.json",
            MCP: None,
            EXECUTABLE: ".github/scripts/{name}",
        },
        "notes": (
            "Parts are loaded from fixed folders rather than a bundle, so there is no manifest "
            "and no install step -- committing the file is the install. Note the doubled "
            "extensions: a subagent is <name>.agent.md and a command is <name>.prompt.md, "
            "where both of the other two use a bare .md. Repo-local, so nothing relocates at "
            "install: an executable's rendered path is already the reference a hook command "
            "needs, no plugin_root token to compose -- that token pair is for reading PLUGINS "
            "this format did not build, not its own repo-local hooks. .github/scripts/ keeps "
            "the vendor's own namespace convention; promptFileLocations.ts imposes no "
            "restriction here, so this is a chosen convention, not a vendor-mandated path."
        ),
        "verified": {
            "method": "source read: src/vs/workbench/contrib/chat/common/promptSyntax/config/promptFileLocations.ts",
            "date": "2026-08-26",
        },
    },
    "copilot": {
        "unit": "plugin",
        "manifest": "plugin.json",
        "manifest_format": "json",
        "manifest_fixed": {"$schema": "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"},
        "project_root": "{bundle}",
        "plugin_root": ("${PLUGIN_ROOT}",),
        "parts": {
            SKILL: "skills/{name}/SKILL.md",
            SUBAGENT: "com.github.copilot/agents/{name}.agent.md",
            COMMAND: None,
            HOOKS: "com.github.copilot/hooks/hooks.json",
            MCP: "mcp.json",
            EXECUTABLE: "scripts/{name}",
        },
        "notes": (
            "skills/ and mcp.json are the standard's own portable component types -- "
            "byte-identical skills/{name}/SKILL.md to every other plugin format here -- found "
            "by location like the manifest fields say. Everything else Copilot can hold "
            "(agents, hooks, and slash commands) is client-specific and lives under "
            "com.github.copilot/, which other clients ignore so the bundle stays portable. "
            "scripts/ sits at the bundle root, outside the namespace, exactly as the vendor's "
            "own example places a hook's script -- referenced via ${PLUGIN_ROOT}, the token "
            "this format defines (NOT ${CLAUDE_PLUGIN_ROOT}, which is the Legacy Copilot "
            "format's spelling, alongside ${PLUGIN_ROOT}, per the same vendor table). "
            "See MATRIX['copilot'] for whether these hooks actually run once installed -- "
            "the honesty gate this row exists to pass."
        ),
        "verified": {
            "method": "vendor source read from a clone: microsoft/vscode-docs "
            "docs/agent-customization/agent-plugins.md -- the directory example, the plugin "
            "manifest field table ($schema required), the plugin-format auto-detection rule "
            "(no $schema falls back to the unrelated Legacy Copilot format), and the "
            "plugin-root token table (Agent Plugins 1.0: ${PLUGIN_ROOT} only)",
            "date": "2026-08-29",
        },
    },
}

from .packaging_limits import ALSO_READS, PART_LIMITS, UNRECORDED  # noqa: E402,F401
