#!/usr/bin/env python3
"""The experiment probe, as source text.

Unlike the capture probe (tools/probe_source.py), this one is *designed to interfere*.
It denies, it crashes, it stalls -- that is the measurement. A probe that always allows
can tell you the shape of a payload but never whether `deny` is honoured or what happens
when a hook dies, which are the two claims the matrix leads with.

Because it interferes, it is only ever installed into a scratch workspace the harness
created and will delete. tools/experiment.py enforces that; nothing here is ever wired
into a config a person actually works in.

The answering trials render their reply **at run time, from the payload they were
actually handed** -- `adapter.parse()` then `adapter.respond()`, the same two calls a real
handler makes. Pre-baking the reply from a synthesized event would have tested a payload
nobody sent. It also means a trial can fail because agentseam spoke the dialect wrongly,
which is a finding worth having rather than one to design away.

Each trial writes one JSON line to `<record_dir>/invocations.jsonl` before it answers, so
"the hook never fired" is distinguishable from "the hook fired and allowed" -- the
difference between an agent with no enforcement point and one whose enforcement point
said yes. At the Stop gate the line count is the measurement itself, because a refused
agent goes round again and the hook fires again; the line carries the *value* of
`stop_hook_active` so a re-fire is attributable to the block rather than merely counted.
"""

from __future__ import annotations

#: Trial name -> what it measures. Surfaced by `experiment.py list`.
BEHAVIOURS = {
    "allow": "Permissive answer in the agent's dialect. Baseline: hooks do not break normal operation.",
    "deny": "Refusal in the agent's dialect. Measures whether deny actually blocks.",
    "crash": "No output, exit 1. Measures fail-open vs fail-closed when a hook dies.",
    "silence": "No output, exit 0. Disambiguates 'silence is an allow' from 'silence is an error'.",
    "timeout": "Sleeps past the agent's hook timeout. Measures the fail mode under a stall.",
    "transform": "Rewrites the tool input. Measures whether the rewritten input is what runs.",
    "unknown": "Answers with a decision verb no vendor defines. Measures tolerance for the unrecognised.",
    "escalate": "Defers to the host's own approval path. Measures what happens with nobody there to answer.",
}

#: Trials that answer nothing at all. Everything else goes through parse/respond.
SILENT_TRIALS = ("crash", "silence", "timeout")

#: How long the `timeout` trial sleeps -- longer than every vendor hook timeout we know of
#: (Claude Code 60s, Cursor 30s). The harness caps the whole trial well above this, so a
#: stalled agent is still observed rather than killed alongside the probe.
TIMEOUT_SLEEP_SECONDS = 90

_TEMPLATE = """#!/usr/bin/env python3
# agentseam experiment probe -- trial: %(trial)s
# INTERFERES ON PURPOSE. Scratch workspaces only. See tools/experiment_probe.py.
import json, os, sys, time

TRIAL = %(trial)r
RECORD = %(record)r
AGENT = %(agent)r
TRIGGER_ALT = %(trigger_alt)r
sys.path.insert(0, %(src)r)

raw = sys.stdin.buffer.read()
try:
    payload = json.loads(raw.decode("utf-8-sig"))
except Exception:
    payload = None

# Recorded before answering: a probe that dies mid-answer still proves it was reached.
try:
    with open(os.path.join(RECORD, "invocations.jsonl"), "a", encoding="utf-8") as fh:
        fh.write(json.dumps({
            "trial": TRIAL,
            "keys": sorted(payload) if isinstance(payload, dict) else None,
            "parsed": payload is not None,
            "bytes": len(raw),
            # The value, not just the key: at Stop this is how the agent says "you
            # already refused me once", which is what makes a re-fire attributable.
            "stop_hook_active": payload.get("stop_hook_active") if isinstance(payload, dict) else None,
        }) + "\\n")
except Exception:
    pass

if TRIAL == "crash":
    sys.stderr.write("agentseam experiment: deliberate failure\\n")
    sys.exit(1)
if TRIAL == "silence":
    sys.exit(0)
if TRIAL == "timeout":
    time.sleep(%(sleep)d)
    sys.exit(0)

if TRIAL == "unknown":
    # Not constructible through Decision, which is the point: a verb no vendor defines.
    sys.stdout.write(json.dumps({"hookSpecificOutput": {
        "hookEventName": (payload or {}).get("hook_event_name", "PreToolUse"),
        "permissionDecision": "quarantine"}}))
    sys.exit(0)

from agentseam import adapters, contract

adapter = adapters.get(AGENT)
event = adapter.parse(payload)
decision = {
    "allow": lambda: contract.Decision.allow(),
    "deny": lambda: contract.Decision.deny("agentseam experiment: deny trial"),
    "transform": lambda: contract.Decision.transform(
        {"command": TRIGGER_ALT}, "agentseam experiment: transform trial"),
    "escalate": lambda: contract.Decision.escalate("agentseam experiment: escalate trial"),
}[TRIAL]()
text, code = adapter.respond(decision, event)
sys.stdout.write(text)
sys.exit(code)
"""


def render(trial, record_dir, *, agent, src_dir, trigger_alt):
    """Probe source for one trial, with this run's paths and agent baked in."""
    if trial not in BEHAVIOURS:
        raise ValueError("unknown trial: %r (have: %s)" % (trial, ", ".join(sorted(BEHAVIOURS))))
    return _TEMPLATE % {
        "trial": trial,
        "record": record_dir,
        "agent": agent,
        "src": src_dir,
        "trigger_alt": trigger_alt,
        "sleep": TIMEOUT_SLEEP_SECONDS,
    }
