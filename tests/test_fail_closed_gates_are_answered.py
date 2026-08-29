"""Every gate installed fail-closed must be answered, because silence there is an error.

The sixth invariant, and the only one resting on a controlled live experiment rather than
on source or documentation.

Cursor 3.17.8, Windows, 2026-08-28, two trials differing in one key:

    hooks.json                                    hook            result
    beforeShellExecution, no failClosed           exit 0, silent  `echo hello` RAN
    beforeShellExecution, failClosed: true        exit 0, silent  BLOCKED by hook

So an empty response at a Cursor gate is not a refusal and not an abstention -- it is a
hook ERROR. Fail-open ignores it; fail-closed refuses on it. Both readings the matrix had
carried since #23 collapse to the second, and the earlier note's "silence blocks" was true
only because `hook_config()` set failClosed on every gate with no way to opt out.

That makes a specific defect possible, and cheap to commit: make one Cursor gate silent on
a bare ALLOW -- the direction four other adapters were deliberately moved in #62 and #64 --
and every allowed tool call is blocked, on the vendor's strongest posture, with no error
anyone would attribute to the guardrail. The user would see their agent refuse everything.

Hence: wherever `hook_config()` marks an entry fail-closed, `respond()` must SAY something
at that event for every outcome a handler can return. The gate we hardened is the gate that
cannot be answered with nothing.

Cursor is the only adapter that takes `fail_closed` today. The test is written against the
capability rather than against Cursor, so an adapter that gains it is covered on arrival
rather than remembered about.
"""

from __future__ import annotations

import inspect
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentseam import Decision, adapters  # noqa: E402

#: Keys a hook_config may use to ask a vendor for fail-closed behaviour. One today; named
#: rather than inferred, so a new spelling is a deliberate addition here.
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


@pytest.mark.parametrize("agent", _fail_closed_adapters())
def test_a_fail_closed_gate_is_never_answered_with_silence(agent):
    mod = adapters.get(agent)
    config = mod.hook_config(sorted(getattr(mod, "REVERSE_EVENT_MAP", {})), "CMD")
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
