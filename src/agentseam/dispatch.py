"""The dispatcher: stdin -> Event -> your handler -> vendor dialect -> stdout/exit."""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
import traceback

from . import adapters
from .allow_semantics import VOUCH_SPEAKS, WARN_SPEAKS
from .contract import PRE_TOOL, PROMPT_SUBMIT, STOP, TRANSFORM, UNKNOWN, VOUCH, WARN, Decision
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

#: How an installed hook knows its agent without guessing: `install` writes the agent's name as
#: the last argument of the hook command, and a wrapper may set this variable instead.
AGENT_ENV = "AGENTSEAM_AGENT"

#: Events where a host reads the hook's silence as a verdict. A payload nobody (or more than one
#: adapter) claims cannot be answered in dialect, so here it is refused rather than passed.
VERDICT_EVENTS = (PRE_TOOL, PROMPT_SUBMIT, STOP)

UNRECOGNIZED = "unrecognized payload"
#: Evidence keys on that refusal: who claimed the payload, and the one line `run()` reports.
CLAIMANTS = "claimants"
DISPATCH_NOTE = "dispatch_note"

_BIND_HINT = "bind the agent: reinstall with `agentseam install`, or call run(handler, agent=...)"


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


_STDERR_FD = 2


def _divert_fd1():
    """Point fd 1 at stderr (devnull if there is none); the saved fd 1, or None if it could not."""
    try:
        saved = os.dup(1)
    except OSError:
        return None
    # With fd 2 closed, dup() hands back 2 itself, and "stderr" would be stdout again.
    if saved > _STDERR_FD:
        with contextlib.suppress(OSError):
            os.dup2(_STDERR_FD, 1)
            return saved
    sink = os.open(os.devnull, os.O_WRONLY)
    os.dup2(sink, 1)
    os.close(sink)
    return saved


def _flush(streams):
    """Flush each stream that exists; a broken one is no reason to lose the verdict."""
    for stream in streams:
        if stream is not None:
            with contextlib.suppress(Exception):
                stream.flush()


@contextlib.contextmanager
def _stdout_to_stderr():
    """While a handler runs, whatever it prints -- itself or a child process -- goes to stderr.

    Stdout is the verdict channel: a handler's stray `print` ahead of the JSON makes the host
    fail to parse it, and Claude Code and Gemini CLI then treat the hook as a non-blocking
    error -- a deny became an allow, witnessed live.
    """
    sink = sys.stderr if sys.stderr is not None else io.StringIO()
    held = (sys.stdout, sys.__stdout__)
    _flush(held)
    saved = _divert_fd1()
    try:
        with contextlib.redirect_stdout(sink):
            yield
    finally:
        if saved is not None:
            # A stream the handler held on to (sys.__stdout__, a reference cached at import)
            # buffers past redirect_stdout; flushed now it lands on stderr, not after the verdict.
            _flush((sink, *held))
            os.dup2(saved, 1)
            os.close(saved)


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


def bound_agent(argv=None, environ=None):
    """The agent `install` bound this hook to, or None for a hook wired by hand.

    AGENT_ENV wins; else the command's last argument, when it names an adapter. Either way the
    payload's own markers are never consulted: `detect()` is the fallback, not the authority.
    """
    env = (os.environ if environ is None else environ).get(AGENT_ENV)
    if env in adapters.ADAPTERS:
        return env
    args = sys.argv if argv is None else argv
    last = args[-1] if len(args) > 1 else None
    return last if last in adapters.ADAPTERS else None


def _unrecognized(raw):
    """No adapter, or more than one, claims `raw`.

    Silent at an observation-only event; a refusal where the host would read silence as a
    verdict. Which event it is, no adapter can say with authority, so it is read the way each
    claimant parses it -- the way any name-mapping adapter does, when none claims a named one.
    """
    claimants = adapters.claimants(raw)
    gates = sorted({adapters.get(name).parse(raw).event for name in adapters.readers(raw)} & set(VERDICT_EVENTS))
    if not gates:
        return "", 0, None, Decision.allow(UNRECOGNIZED)
    who = ", ".join(claimants) if claimants else "no adapter"
    note = "agentseam: refusing a %s payload claimed by %s (exactly one is needed); %s\n" % (gates[0], who, _BIND_HINT)
    evidence = {CLAIMANTS: claimants, DISPATCH_NOTE: note}
    return "", DISPATCH_FAILURE_EXIT, None, Decision.deny(UNRECOGNIZED, evidence=evidence)


def handle(raw, handler, agent=None):
    """Pure core: raw payload + handler -> (stdout_text, exit_code, event, decision)."""
    name = agent or adapters.detect(raw)
    if not name:
        return _unrecognized(raw)
    mod = adapters.get(name)
    event = mod.parse(raw)
    if event.event == UNKNOWN:
        return "", 0, event, Decision.allow("unmapped vendor event")
    try:
        with _stdout_to_stderr():
            result = handler(event)
        decision = _coerce(result)
    except Exception as exc:  # noqa: BLE001 (whatever the handler's defect, the outcome is the same:
        # this event is refused in the vendor's own dialect. Letting it escape exits the hook
        # process with 1 and a traceback, which every host reads as a non-blocking error --
        # the crash trial in data/recordings witnessed Claude Code run the tool regardless)
        decision = _refusal(exc)
    decision = degrade(decision, event, name)
    text, code = mod.respond(decision, event)
    return text, code, event, decision


def _report(text):
    """Best effort, never raising: a diagnostic must not pre-empt the refusal it accompanies.

    A hook's stderr is whatever the host gave it -- closed (then `sys.stderr` is None and a
    bare traceback print would land on stdout, inside the verdict), a console code page that
    cannot hold the payload text quoted in the exception, a pipe nobody reads.
    """
    try:
        sys.stderr.write(text)
        sys.stderr.flush()
    except Exception:  # noqa: BLE001 (every failure here means the same thing: nowhere to say
        # it -- and the verdict on stdout is the message that matters)
        return


def _read_payload(stream):
    """Read BYTES and decode UTF-8 ourselves rather than trusting the platform locale."""
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        return buffer.read().decode("utf-8-sig", errors="replace")
    return stream.read().lstrip("\ufeff")


def _quiet_exit(exit):  # noqa: A002 (the same keyword run() takes)
    if exit:
        sys.exit(0)
    return 0


def run(handler, agent=None, stdin=None, stdout=None, *, exit=True):  # noqa: A002 (matches
    # sys.exit's name on purpose; every caller and the bundled runtime.py.tmpl's main() already
    # speak `exit=` as a keyword, so renaming it would be the breaking change, not keeping it)
    """Read one payload from stdin, dispatch, emit the vendor response, exit."""
    agent = agent or bound_agent()
    stream = stdin or sys.stdin
    out = stdout or sys.stdout
    try:
        raw = json.loads(_read_payload(stream))
    except json.JSONDecodeError:
        # Text that is not JSON: the host's fault, not the agent's, so no verdict is given.
        return _quiet_exit(exit)
    except (ValueError, RecursionError, MemoryError):
        # Valid JSON this process cannot decode (nested past the recursion limit, an integer
        # past the digit limit): no Event can be built, so the one refusal left is the host's
        # blocking exit code. A stdin that cannot be read at all is still no payload.
        _report(traceback.format_exc())
        if exit:
            sys.exit(DISPATCH_FAILURE_EXIT)
        return DISPATCH_FAILURE_EXIT
    except Exception:  # noqa: BLE001 (the outermost boundary before any handler runs: an
        # unreadable stdin is not the agent's fault to pay for, whatever shape the failure takes)
        return _quiet_exit(exit)
    try:
        text, code, _event, decision = handle(raw, handler, agent)
    except Exception:  # noqa: BLE001 (past the handler, which handle() already answers for: an
        # adapter or dispatcher fault on a payload it did decode. There is no Event to answer
        # in dialect, so the one refusal left is the host's blocking exit code)
        _report(traceback.format_exc())
        text, code = "", DISPATCH_FAILURE_EXIT
    else:
        evidence = decision.evidence if isinstance(decision.evidence, dict) else {}
        _report(evidence.get(HANDLER_TRACEBACK) or evidence.get(DISPATCH_NOTE) or "")
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
