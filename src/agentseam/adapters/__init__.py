"""Per-agent adapters: parse a vendor payload -> Event; speak a Decision in vendor dialect."""

from __future__ import annotations

from .._data import load
from . import vscode_copilot
from ._family import bind

#: Every vendor but one is a family engine (D3-D5) bound to its data/vendors entry;
#: vscode_copilot stays a dialect module -- its three-path claims() and memory-tool
#: branching are beyond what the flat config may carry (§3.1).
_CONFIG_DRIVEN = (
    "antigravity",
    "claude_code",
    "codex_cli",
    "cursor",
    "devin",
    "gemini_cli",
    "grok",
    "junie",
    "kimi_code",
    "tabnine",
    "windsurf",
)

ADAPTERS = {vscode_copilot.AGENT: vscode_copilot}
ADAPTERS.update({agent: bind(load("vendors/%s.json" % agent)) for agent in _CONFIG_DRIVEN})


def get(agent):
    try:
        return ADAPTERS[agent]
    except KeyError as exc:
        raise KeyError("no adapter for agent %r (have: %s)" % (agent, ", ".join(sorted(ADAPTERS)))) from exc


def detect(raw):
    """Best-effort agent identification from a raw payload."""
    claims = [name for name, mod in sorted(ADAPTERS.items()) if mod.claims(raw)]
    return claims[0] if len(claims) == 1 else None


def shell_tools(agent):
    """Tool names a shell command arrives under, or () where none is established."""
    return tuple(getattr(get(agent), "SHELL_TOOLS", ()))
