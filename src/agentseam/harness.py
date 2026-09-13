"""How to drive each vendor's agent headlessly, and what voids a run against it.

Everything here was paid for by running real agents and losing runs to it. An argv is the
cheap part; what cost something is the rest -- that Codex gates its sandbox on project
trust recorded outside the workspace, that a file the agent creates on Windows is owned by
an account the harness cannot read, that `--full-auto` stopped existing between two minor
versions. A harness that does not know those things does not fail loudly. It produces a
run that looks like a measurement and measured nothing.

So this module's one invariant:

    An agent with no recorded harness row gets a refusal, never a guessed command line.

A guess is the failure mode worth designing against, because its output is indistinguishable
from a real result. `void_markers` is the same discipline pointed at the run's output: it
names the evidence that an agent was *prevented* from working, which is not at all the same
as an agent that looked and chose to do nothing. The first measured nothing; the second is
the data point.

Placement, not policy: agentseam owns how to reach a vendor. What to ask it, and what
counts as a pass, stays with the consumer.
"""

from __future__ import annotations

import os as _os
import shlex as _shlex
import subprocess as _subprocess

from ._data import load

_DATA = load("harness.json")

#: Agent id -> how to drive it. Canonical ids, so a row lines up with MATRIX's.
HARNESS = _DATA["agents"]

#: Output proving the agent was refused rather than unproductive. Checked only when the
#: agent changed nothing: an agent that hit a refusal and recovered went on to edit
#: something, and that gate is the whole discriminator.
VOID_MARKERS = tuple(_DATA["void_markers"])

#: Text that betrays the operator's own standing instructions reaching the agent, which
#: makes a run a measurement of the instructions rather than of the policy.
INSTRUCTION_MARKERS = tuple(_DATA["instruction_markers"])

#: The token the probe's driver template carries where the prompt goes. Named by the probe,
#: not by us -- experiment_driver.drive_real() substitutes a JSON-quoted string for it.
DRIVER_PROMPT_SLOT = "{prompt}"

PROMPT_PLACEHOLDER = "__PROMPT__"
MODEL_PLACEHOLDER = "__MODEL__"


class NoHarnessError(LookupError):
    """No recorded way to drive this agent headlessly."""


def agents():
    """Agents with a recorded headless invocation."""
    return sorted(HARNESS)


def row(agent):
    """The recorded harness row for `agent`, or raise NoHarnessError."""
    try:
        return HARNESS[agent]
    except KeyError:
        raise NoHarnessError(
            "no harness recorded for %r: agentseam knows how to drive %s. A guessed "
            "command line produces a run that looks like a measurement and is not one -- "
            "record the invocation first." % (agent, ", ".join(agents()))
        ) from None


def argv(agent, prompt, *, model=None, hooked=False):
    """The command line that runs `prompt` against `agent`, as a list.

    `hooked=True` asks for the variant whose tool permissions are narrowed to the policy
    under test. An agent with no recorded hooked variant refuses: falling back to the
    unhooked argv would silently measure the wrong arm.
    """
    record = row(agent)
    key = "hooked_argv" if hooked else "argv"
    template = record.get(key)
    if template is None:
        raise NoHarnessError("no %r recorded for %r: %s" % (key, agent, record.get("hooked_note") or "not established"))
    line = [part.replace(PROMPT_PLACEHOLDER, prompt) for part in template]
    if model is not None:
        line = _with_model(record, line, model, agent)
    return line


def _with_model(record, line, model, agent):
    """Insert the model flag at the position this vendor accepts it.

    The position cannot be inferred from the argv -- Codex takes it after the subcommand,
    Claude Code before the prompt flag -- so it is recorded per agent and read, not guessed.
    """
    flag = record.get("model_argv")
    at = record.get("model_at")
    if flag is None or at is None:
        raise NoHarnessError("no model flag recorded for %r: its position cannot be inferred" % agent)
    rendered = [part.replace(MODEL_PLACEHOLDER, model) for part in flag]
    return line[:at] + rendered + line[at:]


def is_void(output):
    """Whether `output` shows the agent was prevented from working.

    The caller applies the gate: check this only for a run that changed nothing.
    """
    lowered = (output or "").lower()
    return any(marker in lowered for marker in VOID_MARKERS)


def void_reason(output):
    """The first void marker present in `output`, or None."""
    lowered = (output or "").lower()
    for marker in VOID_MARKERS:
        if marker in lowered:
            return marker
    return None


def leaked_instructions(output):
    """Instruction markers present in `output` -- non-empty means the run is instructed."""
    lowered = (output or "").lower()
    return tuple(m for m in INSTRUCTION_MARKERS if m.lower() in lowered)


def isolation(agent):
    """What this agent needs to run in isolation, as recorded prose, or None."""
    return row(agent).get("isolation")


def creates_files_as(agent):
    """Recorded prose on file ownership of what the agent creates, or None."""
    return row(agent).get("creates_files_as")


def driver_command(agent, *, model=None, hooked=False):
    """The recorded invocation as a probe driver template, with `{prompt}` where the prompt goes.

    This is what removes the hand-typed driver string from a witness run: the registry already
    knows how to reach the vendor, so the operator names the agent and nothing else.

    Quoted for the platform actually running it. `shlex.quote` is POSIX-only, and these runs
    happen on a Windows machine as often as not -- a POSIX-quoted argument there is not a
    slightly-wrong command line, it is a different one. The prompt slot is left unquoted on
    purpose: `drive_real` substitutes an already-quoted JSON string for it.
    """
    slot = "\x00agentseam-prompt\x00"
    parts = argv(agent, slot, model=model, hooked=hooked)
    rendered = [DRIVER_PROMPT_SLOT if part == slot else _quote_one(part) for part in parts]
    if any(slot in part for part in rendered):
        raise NoHarnessError(
            "%r builds its prompt inside a larger argument, which this template cannot "
            "express; drive it with an explicit --driver string." % agent
        )
    return " ".join(rendered)


def _quote_one(part):
    """Shell-quote one argument the way the running platform's shell reads it."""
    if _os.name == "nt":
        return _subprocess.list2cmdline([part])
    return _shlex.quote(part)
