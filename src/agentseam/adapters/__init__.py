"""Per-agent adapters: parse a vendor payload -> Event; speak a Decision in vendor dialect."""

from __future__ import annotations

from .._data import load
from . import (
    antigravity,
    cursor,
    gemini_cli,
    grok,
    junie,
    tabnine,
    vscode_copilot,
    windsurf,
)
from ._family import bind

#: hook_json vendors driven by engine + data/vendors entry (dialect-families.md D3);
#: vscode_copilot stays a dialect module -- its three-path claims() and memory-tool
#: branching are beyond what the flat config may carry (§3.1).
_CONFIG_DRIVEN = ("claude_code", "codex_cli", "devin", "kimi_code")

ADAPTERS = {
    antigravity.AGENT: antigravity,
    cursor.AGENT: cursor,
    gemini_cli.AGENT: gemini_cli,
    grok.AGENT: grok,
    junie.AGENT: junie,
    tabnine.AGENT: tabnine,
    vscode_copilot.AGENT: vscode_copilot,
    windsurf.AGENT: windsurf,
}
ADAPTERS.update({agent: bind(load("vendors/%s.json" % agent)) for agent in _CONFIG_DRIVEN})


def get(agent):
    try:
        return ADAPTERS[agent]
    except KeyError:
        raise KeyError("no adapter for agent %r (have: %s)" % (agent, ", ".join(sorted(ADAPTERS))))


def detect(raw):
    """Best-effort agent identification from a raw payload."""
    claims = [name for name, mod in sorted(ADAPTERS.items()) if mod.claims(raw)]
    return claims[0] if len(claims) == 1 else None


def shell_tools(agent):
    """Tool names a shell command arrives under, or () where none is established."""
    return tuple(getattr(get(agent), "SHELL_TOOLS", ()))
