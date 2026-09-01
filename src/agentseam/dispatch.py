"""The dispatcher: stdin -> Event -> your handler -> vendor dialect -> stdout/exit."""

from __future__ import annotations

import json
import sys

from . import adapters
from .allow_semantics import VOUCH_SPEAKS, WARN_SPEAKS
from .contract import TRANSFORM, UNKNOWN, VOUCH, WARN, Decision
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
    """Reduce a decision to what the agent can actually honor, honestly."""
    agent = agent or event.agent
    cap = capability(agent, event.event)
    if decision.outcome == TRANSFORM and not cap["transform"]:
        evidence = dict(decision.evidence)
        evidence["degraded_from"] = TRANSFORM
        return Decision.escalate(decision.reason or "input requires modification before it can run", evidence=evidence)
    if decision.outcome == VOUCH and agent not in VOUCH_SPEAKS:
        evidence = dict(decision.evidence)
        evidence["degraded_from"] = VOUCH
        return Decision.allow(decision.reason, evidence=evidence, context=decision.context)
    if decision.outcome == WARN and agent not in WARN_SPEAKS:
        evidence = dict(decision.evidence)
        evidence["degraded_from"] = WARN
        return Decision.allow(decision.reason, evidence=evidence, context=decision.context)
    return decision


def handle(raw, handler, agent=None):
    """Pure core: raw payload + handler -> (stdout_text, exit_code, event, decision)."""
    name = agent or adapters.detect(raw)
    if not name:
        return "", 0, None, Decision.allow("unrecognized payload")
    mod = adapters.get(name)
    event = mod.parse(raw)
    if event.event == UNKNOWN:
        return "", 0, event, Decision.allow("unmapped vendor event")
    decision = degrade(_coerce(handler(event)), event, name)
    text, code = mod.respond(decision, event)
    return text, code, event, decision


def _read_payload(stream):
    """Read BYTES and decode UTF-8 ourselves rather than trusting the platform locale."""
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
        if exit:
            sys.exit(0)
        return 0
    text, code, _event, _decision = handle(raw, handler, agent)
    if text:
        _emit(out, text)
    if exit:
        sys.exit(code)
    return code


def _emit(out, text):
    """Write the vendor response as UTF-8, whatever the platform locale is."""
    buffer = getattr(out, "buffer", None)
    if buffer is not None:
        buffer.write(text.encode("utf-8"))
        buffer.flush()
    else:
        out.write(text)
        out.flush()
