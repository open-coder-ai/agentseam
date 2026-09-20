"""The dispatcher: stdin -> Event -> your handler -> vendor dialect -> stdout/exit."""

from __future__ import annotations

import json
import sys
import traceback

from . import adapters
from .allow_semantics import VOUCH_SPEAKS, WARN_SPEAKS
from .contract import TRANSFORM, UNKNOWN, VOUCH, WARN, Decision
from .matrix import capability


class UnsupportedDecisionError(Exception):
    """Raised when a handler asks for something the agent cannot do at this event."""


#: Evidence keys on the refusal a failed handler earns. Never emitted on the wire: `run()`
#: prints the traceback to stderr, and an in-process caller reads it off the decision.
HANDLER_ERROR = "handler_error"
HANDLER_TRACEBACK = "handler_traceback"

#: Exit code when the dispatcher itself fails on a payload it did decode -- the blocking-error
#: code on every host that has one, with nothing on stdout for the host to misread as a verdict.
DISPATCH_FAILURE_EXIT = 2


def _coerce(result):
    if result is None:
        return Decision.allow()
    if isinstance(result, Decision):
        return result
    raise TypeError("handler must return a Decision or None, got %r" % (type(result),))


def _refusal(exc):
    """A door that cannot decide refuses. Only the failure's class reaches the host: its
    message may quote the very payload content the policy was inspecting."""
    return Decision.deny(
        "policy handler failed (%s); refusing rather than allowing what it could not judge" % type(exc).__name__,
        evidence={HANDLER_ERROR: "%s: %s" % (type(exc).__name__, exc), HANDLER_TRACEBACK: traceback.format_exc()},
    )


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
    try:
        decision = _coerce(handler(event))
    except Exception as exc:  # noqa: BLE001 (whatever the handler's defect, the outcome is the same:
        # this event is refused in the vendor's own dialect. Letting it escape exits the hook
        # process with 1 and a traceback, which every host reads as a non-blocking error --
        # the crash trial in data/recordings witnessed Claude Code run the tool regardless)
        decision = _refusal(exc)
    decision = degrade(decision, event, name)
    text, code = mod.respond(decision, event)
    return text, code, event, decision


def _read_payload(stream):
    """Read BYTES and decode UTF-8 ourselves rather than trusting the platform locale."""
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        return buffer.read().decode("utf-8-sig", errors="replace")
    return stream.read().lstrip("\ufeff")


def run(handler, agent=None, stdin=None, stdout=None, *, exit=True):  # noqa: A002 (matches
    # sys.exit's name on purpose; every caller and the bundled runtime.py.tmpl's main() already
    # speak `exit=` as a keyword, so renaming it would be the breaking change, not keeping it)
    """Read one payload from stdin, dispatch, emit the vendor response, exit."""
    stream = stdin or sys.stdin
    out = stdout or sys.stdout
    try:
        raw = json.loads(_read_payload(stream))
    except Exception:  # noqa: BLE001 (the outermost boundary before any handler runs: malformed
        # or unreadable stdin is not the agent's fault to pay for, whatever shape the failure
        # takes -- narrowing to JSONDecodeError would let a stdin read failure crash the host)
        if exit:
            sys.exit(0)
        return 0
    try:
        text, code, _event, decision = handle(raw, handler, agent)
    except Exception:  # noqa: BLE001 (past the handler, which handle() already answers for: an
        # adapter or dispatcher fault on a payload it did decode. There is no Event to answer
        # in dialect, so the one refusal left is the host's blocking exit code)
        traceback.print_exc()
        text, code = "", DISPATCH_FAILURE_EXIT
    else:
        failure = decision.evidence.get(HANDLER_TRACEBACK)
        if failure:
            sys.stderr.write(failure)
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
