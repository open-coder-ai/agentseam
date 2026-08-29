"""Primitive 3 data, split out of packaging_data.py to keep both under the line budget.

Three tables that are all "the honest gap," not "the format," which is why they live apart
from PACKAGING itself: why a specific agent cannot hold a specific part, which folders an
agent reads that belong to another agent, and which matrix agents have no packaging format
recorded here at all.
"""

from __future__ import annotations

from .packaging_data import COMMAND, EXECUTABLE, HOOKS, MCP, SHARED_SKILL_DIR, SKILL, SUBAGENT

#: Why a specific agent cannot hold a specific part. Without these the generic message
#: ("this format has no place for it") would understate Gemini, which supports MCP servers
#: perfectly well -- just in the manifest rather than in a file of its own.
PART_LIMITS = {
    ("codex_cli", MCP): "MCP servers are declared inside .codex-plugin/plugin.json under "
    "`mcp_servers`, not in a file of their own",
    ("codex_cli", COMMAND): "the manifest reads command paths from a `commands` field, but the "
    "command FILE format was not established here -- a guessed format ships a plugin whose "
    "commands silently do not load",
    ("codex_cli", SUBAGENT): "no subagent field exists in the plugin manifest",
    ("codex_cli", EXECUTABLE): "RawPluginManifest's field list is exhaustive (name, version, "
    "description, keywords, skills, mcp_servers, apps, hooks, interface) and none names a "
    "bundled executable or scripts path; whether an undeclared file elsewhere in the plugin "
    "directory survives installation to be referenced by a hook command was not established here",
    ("cursor", MCP): "no MCP declaration was established for this plugin format",
    ("cursor", COMMAND): "no command format was established for this plugin format",
    ("cursor", SUBAGENT): "no subagent format was established for this plugin format",
    ("cursor", EXECUTABLE): "no scripts/executable location was established for this closed-source "
    "plugin format; the documented layout (.cursor-plugin/, skills/, rules/, mcp.json) names "
    "no place for one",
    ("gemini_cli", MCP): "MCP servers are declared inside gemini-extension.json, not in a file "
    "of their own; a rendered .mcp.json would simply be ignored",
    ("vscode_copilot", MCP): "MCP servers are configured by the editor rather than shipped alongside these parts",
    ("copilot", COMMAND): "com.github.copilot/commands/ is documented as the slash-command "
    "location, but the command FILE format inside it was not established from what was read "
    "here -- a guessed extension ships a plugin whose commands silently do not load, the same "
    "failure mode PART_LIMITS already records for codex_cli",
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
    "devin": "skills provably exist -- its hook loader is documented as following the same "
    "discovery rules as skills and rules -- but their layout was not read here",
    "grok": "subagents provably exist (SubagentStart and SubagentStop hook events), and it has an "
    "extensions system, but neither layout was established here",
    "junie": "extensions provably exist and ship hooks at hooks/hooks.json in the Claude "
    "plugin layout, with ${JUNIE_EXTENSION_ROOT} aliasing ${CLAUDE_PLUGIN_ROOT} -- but the "
    "rest of the extension layout, and how skills and commands sit in it, was not read here",
    "kimi_code": "subagents provably exist (a SubagentStop hook event, and a documented agents "
    "and sub-agents feature) but their layout was not read here",
    "replit": "no packaging format established here",
    "tabnine": "no packaging format established here; vendor documentation is unreachable from this environment",
    "windsurf": "vendor documentation unreachable from the environment this was written in",
    "zed": "no packaging format established here",
}
