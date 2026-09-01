"""Primitive 3 data: how each agent packages reusable parts, and where it looks for them."""

from __future__ import annotations

from ._data import load

SKILL = "skill"
SUBAGENT = "subagent"
COMMAND = "command"
HOOKS = "hooks"
MCP = "mcp"
EXECUTABLE = "executable"
PARTS = (SKILL, SUBAGENT, COMMAND, HOOKS, MCP, EXECUTABLE)

SHARED_SKILL_DIR = ".agents/skills"

#: **${CODEX_PLUGIN_ROOT} is a trap.** It appears in Codex's own TUI hook browser as sample

PACKAGING = load("packaging.json")

from .packaging_limits import ALSO_READS, PART_LIMITS, UNRECORDED  # noqa: E402,F401
