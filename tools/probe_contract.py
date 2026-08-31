"""Which response shape does a vendor actually HONOUR at a given event?"""

from __future__ import annotations

import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
CONTROL = os.path.join(HERE, "probe-contract-mode.txt")
LOG = os.path.join(HERE, "probe-contract-log.jsonl")

SHAPES = ("toplevel", "nested", "exit2", "off")


def _reply(shape, event, reason):
    """(stdout, exit_code) for one candidate shape. `off` is the control: say nothing."""
    if shape == "toplevel":
        return json.dumps({"decision": "block", "reason": reason}), 0
    if shape == "nested":
        out = {"hookEventName": event, "permissionDecision": "deny", "permissionDecisionReason": reason}
        return json.dumps({"hookSpecificOutput": out}), 0
    if shape == "exit2":
        sys.stderr.write(reason + "\n")
        return "", 2
    return "", 0


def _control():
    """(event_to_act_on, shape). Absent or unreadable control file means do nothing."""
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
        sys.exit(0)
