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
    "cline",
    "claude_code",
    "codex_cli",
    "cursor",
    "devin",
    "factory_droid",
    "gemini_cli",
    "goose",
    "grok",
    "junie",
    "kimi_code",
    "mistral_vibe",
    "openhands",
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


def claimants(raw):
    """Every adapter that claims `raw`, in name order."""
    return [name for name, mod in sorted(ADAPTERS.items()) if mod.claims(raw)]


def detect(raw):
    """Best-effort agent identification from a raw payload: the one claimant, else None."""
    claims = claimants(raw)
    return claims[0] if len(claims) == 1 else None


def _names_an_event(raw):
    """True when the payload spells an event name under a key some adapter reads one from."""
    keys = {key for mod in ADAPTERS.values() for key in getattr(mod, "EVENT_KEYS", ())}
    return isinstance(raw, dict) and any(isinstance(raw.get(key), str) for key in keys)


def readers(raw):
    """Whose reading of `raw`'s event counts when `detect()` declines: the claimants; else, when
    the payload names its event, every adapter that maps names -- one that infers the event from
    shape alone has no say over a payload it did not claim; else nobody, and the event is unknown."""
    claims = claimants(raw)
    if claims:
        return claims
    if not _names_an_event(raw):
        return []
    return [name for name, mod in sorted(ADAPTERS.items()) if mod.EVENT_MAP]


def shell_tools(agent):
    """Tool names a shell command arrives under, or () where none is established."""
    return tuple(getattr(get(agent), "SHELL_TOOLS", ()))
