"""Primitive 4 data: where each agent keeps its permission config, and what that config can say."""

from __future__ import annotations

from ._data import load

ALLOW = "allow"
ASK = "ask"
DENY = "deny"
ACTIONS = (ALLOW, ASK, DENY)

SHELL = "shell"
FILE_READ = "file_read"
FILE_WRITE = "file_write"
NETWORK_FETCH = "network_fetch"
MCP = "mcp"
CAPABILITIES = (SHELL, FILE_READ, FILE_WRITE, NETWORK_FETCH, MCP)

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

CAPABILITY = load("permissions-capability.json")

UNRECORDED = load("permissions-unrecorded.json")
