"""Which response shape does a vendor actually HONOUR at a given event?

`capture.py` answers what an agent sends. This answers the other half, which no capture
can: of the candidate reply shapes, which one the agent actually reads. That question has
produced four real defects in this project already -- a gate shape emitted at an event that
reads a different one is not a louder refusal, it is no refusal -- and it cannot be settled
from documentation. Two reads of the same vendor page disagreed on it (2026-08-28), which is
the evidence quality that put camelCase event names in the Codex adapter for its whole life.

How it works. The probe is wired at the event under test and replies with ONE candidate
shape per trial, chosen by a control file rather than by editing the agent's settings -- so
a trial is a file write, not a re-install and a session restart. Whether the reply was
honoured is then read off the agent's own behaviour, not off the probe:

  prompt_submit  the trial prompt asks the agent to write a marker file. Marker present
                 means the prompt reached the model, so the shape was NOT honoured.
  stop           a honoured block makes the agent continue instead of stopping, so the Stop
                 hook fires again with stop_hook_active true. That second record IS the
                 evidence, and the probe refuses to block on it -- respecting the vendor's
                 own loop guard rather than trusting it.

Both signals are things the agent does, not things the probe claims, which is the point:
the last time an agent was asked to report on itself here it confabulated the answer.
"""

from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL = os.path.join(HERE, "probe-contract-mode.txt")
LOG = os.path.join(HERE, "probe-contract-log.jsonl")

#: Candidate shape -> how to say "refuse" in it. Each is a real dialect some vendor in this
#: project speaks, which is why they are the candidates: the question is which one THIS
#: vendor reads, and the honest answer has to come from trying them.
#:
#: `nested` is what agentseam emits at every Claude Code event today. `toplevel` is what the
#: vendor-truth backlog proposed instead. `exit2` is what the current vendor reference seems
#: to say. All three are live hypotheses; that is the whole reason for running this.
SHAPES = ("toplevel", "nested", "exit2", "off")


def _reply(shape, event, reason):
    """(stdout, exit_code) for one candidate shape. `off` is the control: say nothing."""
    if shape == "toplevel":
        return json.dumps({"decision": "block", "reason": reason}), 0
    if shape == "nested":
        out = {"hookEventName": event, "permissionDecision": "deny", "permissionDecisionReason": reason}
        return json.dumps({"hookSpecificOutput": out}), 0
    if shape == "exit2":
        # The reason goes to stderr, which is where every vendor that honours exit 2 reads it.
        sys.stderr.write(reason + "\n")
        return "", 2
    return "", 0


def _control():
    """(event_to_act_on, shape). Absent or unreadable control file means do nothing.

    Deliberately fail-quiet: this probe runs inside somebody's real session, and a probe
    that can crash the hook is a probe that can break the session.
    """
    try:
        with open(CONTROL, encoding="utf-8-sig") as fh:
            raw = fh.read().strip()
    except OSError:
        return None, "off"
    if ":" not in raw:
        return None, "off"
    event, _, shape = raw.partition(":")
    shape = shape.strip()
    return event.strip(), shape if shape in SHAPES else "off"


def main():
    try:
        payload = json.loads(sys.stdin.read() or "{}")
    except ValueError:
        payload = {}
    event = payload.get("hook_event_name") or payload.get("hookEventName") or "?"
    target, shape = _control()
    active = bool(payload.get("stop_hook_active"))

    acting = event == target and not active
    # stop_hook_active means the agent is ALREADY continuing because a stop hook blocked it.
    # Blocking again is how a stop guard becomes an infinite loop, so the probe declines --
    # and that decline is not a loss, because the record below is already the evidence.
    record = {
        "at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "event": event,
        "target": target,
        "shape": shape,
        "acting": acting,
        "stop_hook_active": active,
    }
    fd = os.open(LOG, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, (json.dumps(record, sort_keys=True) + "\n").encode("utf-8"))
    finally:
        os.close(fd)

    if not acting:
        return 0
    out, code = _reply(shape, event, "agentseam contract probe [%s]" % shape)
    if out:
        sys.stdout.write(out)
        sys.stdout.flush()
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        sys.exit(0)  # never break the session over a diagnostic
