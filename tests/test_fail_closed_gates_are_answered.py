"""Every gate installed fail-closed must be answered, because silence there is an error."""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentseam import Decision, adapters  # noqa: E402
from agentseam.allow_semantics import ALLOW_SEMANTICS, ALLOW_SILENT  # noqa: E402

_FAIL_CLOSED_KEYS = ("failClosed", "fail_closed")

_OUTCOMES = (
    ("allow", lambda: Decision.allow()),
    ("deny", lambda: Decision.deny("policy")),
    ("ask", lambda: Decision.ask("confirm")),
    ("rewrite", lambda: Decision.rewrite({"content": "safe"}, "redacted")),
    ("rewrite-without-input", lambda: Decision.rewrite(None, "needs change")),
)


def _fail_closed_adapters():
    out = []
    for agent in sorted(adapters.ADAPTERS):
        mod = adapters.get(agent)
        if "fail_closed" in inspect.signature(mod.hook_config).parameters:
            out.append(agent)
    return out


def _silence_is_a_hook_error(agent):
    """False where the vendor documents empty stdout as a passthrough even fail-closed (mistral_vibe's strict)."""
    return ALLOW_SEMANTICS.get(agent, (None,))[0] != ALLOW_SILENT


def _marked_fail_closed(entry):
    return any(entry.get(key) for key in _FAIL_CLOSED_KEYS)


def _probe(event_name, agent):
    return {
        "conversation_id": "c",
        "generation_id": "g",
        "hook_event_name": event_name,
        "hookEventName": event_name,
        "command": "ls",
        "cwd": "/repo",
        "sandbox": False,
        "tool_name": "Bash",
        "tool_input": {"command": "ls"},
        "prompt": "p",
        "client_type": agent,
    }


def test_some_adapter_still_asks_for_fail_closed():
    """If this goes empty the invariant below is vacuously true, which is worth knowing."""
    assert _fail_closed_adapters(), "no adapter takes fail_closed -- has the capability moved?"


@pytest.mark.parametrize("agent", [a for a in _fail_closed_adapters() if _silence_is_a_hook_error(a)])
def test_a_fail_closed_gate_is_never_answered_with_silence(agent):
    mod = adapters.get(agent)
    config = mod.hook_config(sorted(getattr(mod, "REVERSE_EVENT_MAP", {})), "CMD", fail_closed=True)
    silent = []
    for event_name, entries in sorted(config.get("hooks", {}).items()):
        if not any(_marked_fail_closed(e) for e in entries if isinstance(e, dict)):
            continue
        parsed = mod.parse(_probe(event_name, agent))
        for label, make in _OUTCOMES:
            text, _code = mod.respond(make(), parsed)
            if not text.strip():
                silent.append("%s/%s on %s" % (agent, event_name, label))
    assert not silent, (
        "a gate installed fail-closed answered with silence, which this vendor reads as a "
        "hook error and refuses:\n  " + "\n  ".join(silent)
    )
