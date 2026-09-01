"""Per-agent adapters: parse a vendor payload -> Event; speak a Decision in vendor dialect."""

from __future__ import annotations

from . import (
    antigravity,
    claude_code,
    codex_cli,
    cursor,
    devin,
    gemini_cli,
    grok,
    junie,
    kimi_code,
    tabnine,
    vscode_copilot,
    windsurf,
)

ADAPTERS = {
    antigravity.AGENT: antigravity,
    claude_code.AGENT: claude_code,
    codex_cli.AGENT: codex_cli,
    cursor.AGENT: cursor,
    devin.AGENT: devin,
    gemini_cli.AGENT: gemini_cli,
    grok.AGENT: grok,
    junie.AGENT: junie,
    kimi_code.AGENT: kimi_code,
    tabnine.AGENT: tabnine,
    vscode_copilot.AGENT: vscode_copilot,
    windsurf.AGENT: windsurf,
}


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
