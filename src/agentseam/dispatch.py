"""The dispatcher: stdin -> Event -> your handler -> vendor dialect -> stdout/exit.

This is the whole runtime surface for a consumer. Write one function, wire it to any
agent, and agentseam speaks each vendor's protocol for you.

    from agentseam import run, Decision

    def handler(event):
        if event.event == "pre_tool" and "secret" in (event.content or ""):
            return Decision.deny("no secrets in memory files")
        return Decision.allow()

    run(handler)          # reads stdin, writes the right dialect, exits correctly
"""

from __future__ import annotations

import json
import sys

from . import adapters
from .contract import REWRITE, UNKNOWN, Decision
from .matrix import capability


class UnsupportedDecision(Exception):
    """Raised when a handler asks for something the agent cannot do at this event."""


def _coerce(result):
    if result is None:
        return Decision.allow()
    if isinstance(result, Decision):
        return result
    raise TypeError("handler must return a Decision or None, got %r" % (type(result),))


def degrade(decision, event, agent=None):
    """Reduce a decision to what the agent can actually honor, honestly.

    rewrite -> ask (when the agent cannot rewrite): never silently pass the original
    input through, because the handler asked for it to be changed.
    deny at a non-blocking event stays deny; the adapter renders it as a detection so
    the caller can see it was not prevented.
    """
    agent = agent or event.agent
    cap = capability(agent, event.event)
    if decision.outcome == REWRITE and not cap["rewrite"]:
        # Record what this was before it was reduced. Without it, a second degradation
        # downstream reports the wrong cause: an adapter that also cannot `ask` would
        # tell the user confirmation was unavailable, for something that was never a
        # confirmation request.
        evidence = dict(decision.evidence)
        evidence["degraded_from"] = REWRITE
        return Decision.ask(decision.reason or "input requires modification before it can run", evidence=evidence)
    return decision


def handle(raw, handler, agent=None):
    """Pure core: raw payload + handler -> (stdout_text, exit_code, event, decision).

    Testable without touching stdin/stdout, which is how the test suite replays real
    vendor fixtures.
    """
    name = agent or adapters.detect(raw)
    if not name:
        # Unknown shape: allow and say nothing. A dispatcher that fails closed on
        # payloads it does not recognise would break every agent it does not know.
        return "", 0, None, Decision.allow("unrecognized payload")
    mod = adapters.get(name)
    event = mod.parse(raw)
    if event.event == UNKNOWN:
        # A vendor event no adapter maps. The handler is not called: it reasons about the
        # canonical vocabulary, and handing it something outside that vocabulary invites a
        # decision made on a false premise. Allow and say nothing, exactly as for a payload
        # we could not identify at all -- and `event` still comes back, so a caller that
        # wants to log the surprise can.
        return "", 0, event, Decision.allow("unmapped vendor event")
    decision = degrade(_coerce(handler(event)), event, name)
    text, code = mod.respond(decision, event)
    return text, code, event, decision


def _read_payload(stream):
    """Read BYTES and decode UTF-8 ourselves rather than trusting the platform locale.

    Ported from chock, which witnessed the failure on a real Cursor install on Windows:
    the console locale is cp1252, Cursor's UTF-8 BOM became the three characters 'ï»¿',
    json failed on "line 1 column 1" -- and the hook allowed everything while claiming
    enforcement. `utf-8-sig` drops the BOM; `errors="replace"` keeps one stray byte from
    silently disabling the gate. Streams without a binary buffer (tests, embeddings) fall
    back to text with the BOM stripped.
    """
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        return buffer.read().decode("utf-8-sig", errors="replace")
    return stream.read().lstrip("\ufeff")


def run(handler, agent=None, stdin=None, stdout=None, exit=True):
    """Read one payload from stdin, dispatch, emit the vendor response, exit."""
    stream = stdin or sys.stdin
    out = stdout or sys.stdout
    try:
        raw = json.loads(_read_payload(stream))
    except Exception:
        # Malformed input is not the agent's fault to pay for: allow, stay silent.
        if exit:
            sys.exit(0)
        return 0
    text, code, _event, _decision = handle(raw, handler, agent)
    if text:
        out.write(text)
        out.flush()
    if exit:
        sys.exit(code)
    return code
