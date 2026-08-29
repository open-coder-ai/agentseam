"""Per-agent adapters: parse a vendor payload -> Event; speak a Decision in vendor dialect.

An adapter is the ONLY place vendor knowledge lives. Adding an agent = adding a module
here plus a matrix row; no consumer changes.
"""

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
    """Best-effort agent identification from a raw payload.

    Used by the universal dispatcher when the caller did not say which agent it is.
    Returns an agent name or None; never guesses when two adapters both claim it.
    """
    claims = [name for name, mod in sorted(ADAPTERS.items()) if mod.claims(raw)]
    return claims[0] if len(claims) == 1 else None


def shell_tools(agent):
    """Tool names a shell command arrives under, or () where none is established.

    The one question a caller wiring a shell gate must answer, and the one whose wrong answer
    is silent: a `matcher` naming a tool the vendor does not use matches nothing, so the hook
    never fires and the install still reports success.

    () is a claim in the usual sense here -- "not established", not "no shell tool". Guessing
    is the failure this returns () to prevent: a sibling guardrail hardcodes "Bash" for four
    vendors, which is right for the two that speak Claude Code's protocol and unverified for
    the rest.
    """
    return tuple(getattr(get(agent), "SHELL_TOOLS", ()))
