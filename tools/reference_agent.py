#!/usr/bin/env python3
"""A coding agent that behaves exactly as Claude Code is known to behave.

This is not a mock in the testing sense -- it is the protocol, made executable. It reads
the same config the real agent reads, invokes hooks the same way, and interprets answers
by the letter of what has been established about them.

Two things fall out of that:

1. **The harness is testable with no credentials, no network, and no vendor account.**
   Every part of tools/experiment.py can be exercised in CI for free.
2. **`vendor-docs` becomes a measurable position rather than a guess.** Run the harness
   against this and against the real agent; where they disagree, the documentation is
   wrong -- and that delta is a class of finding matrix-evidence.json cannot record today.

**The two grammars matter more than anything else here.** `PreToolUse` (G2) honours
`hookSpecificOutput.permissionDecision`. `Stop` and `UserPromptSubmit` (G1) *ignore* it and
honour only `{"decision": "block"}`, `continue: false`, and exit 2. That is not from the
hooks reference -- two reads of that page disagreed, and one claimed those events had no
JSON decision control at all. It is from the live run recorded in this repository's own
matrix-evidence entry for claude_code, which settled it by observation. Encoding it here
means the reference reproduces a finding that cost someone a real session to establish.

Where the protocol is genuinely silent this raises rather than guessing, because a guess
here would launder itself into evidence.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

CLAUDE_CODE_TIMEOUT_SECONDS = 60

ALLOW, DENY, ASK = "allow", "deny", "ask"

#: Wire event -> which decision grammar the agent applies to the answer.
#: G2 reads permissionDecision; G1 does not. See the module docstring.
GRAMMARS = {"PreToolUse": "G2", "Stop": "G1", "UserPromptSubmit": "G1"}

#: The order a turn visits its gates. A block at an earlier gate means later ones are
#: never reached, which is itself part of what an experiment measures.
TURN = ("UserPromptSubmit", "PreToolUse", "Stop")


class Undocumented(Exception):
    """The protocol does not say what happens here, so the reference will not invent it."""


def _hook_commands(config_path, event):
    """The hook commands wired for `event`, in the order the agent would run them."""
    if not os.path.exists(config_path):
        return []
    with open(config_path, encoding="utf-8") as fh:
        settings = json.load(fh)
    out = []
    for group in settings.get("hooks", {}).get(event, []):
        for hook in group.get("hooks", []):
            if hook.get("type", "command") == "command" and hook.get("command"):
                out.append(hook["command"])
    return out


def _interpret(proc, grammar):
    """(decision, reason, updated_input) from one hook process, under one grammar."""
    if proc.returncode == 2:  # noqa: PLR2004
        # Exit 2 is the blocking error at every gate; stderr is fed back as the reason.
        return DENY, (proc.stderr or "").strip() or "blocked by hook", None
    if proc.returncode != 0:
        # Any other non-zero is a NON-blocking error: surfaced, action proceeds. The
        # documented fail-open, and the single most consequential line in the protocol.
        return ALLOW, "hook error (exit %d), non-blocking" % proc.returncode, None

    text = (proc.stdout or "").strip()
    if not text:
        return ALLOW, "silent success", None
    try:
        body = json.loads(text)
    except ValueError:
        return ALLOW, "non-JSON stdout treated as context", None

    # G1 first, because the interesting case is what it IGNORES.
    if grammar == "G1":
        if body.get("decision") == "block":
            return DENY, body.get("reason") or "blocked by hook", None
        if body.get("continue") is False:
            return DENY, body.get("stopReason") or "stopped by hook", None
        # permissionDecision is not read at these gates. Silently allowing is the
        # observed behaviour, and is exactly how an adapter that emits the wrong shape
        # here looks like it is working.
        return ALLOW, "no G1 decision field (permissionDecision is not read here)", None

    specific = body.get("hookSpecificOutput") or {}
    updated = specific.get("updatedInput")
    decision = specific.get("permissionDecision")
    if decision in (ALLOW, DENY, ASK):
        return decision, specific.get("permissionDecisionReason") or "", updated
    if decision is not None:
        raise Undocumented("unrecognised permissionDecision: %r" % (decision,))
    if body.get("decision") == "block":
        return DENY, body.get("reason") or "blocked by hook", None
    if body.get("continue") is False:
        return DENY, body.get("stopReason") or "stopped by hook", None
    return ALLOW, "no decision field", updated


def _payload(event, *, cwd, command, session_id, stop_hook_active=False):
    """The payload the agent would send at `event`."""
    base = {"session_id": session_id, "cwd": cwd, "hook_event_name": event}
    if event == "PreToolUse":
        base.update({"tool_name": "Bash", "tool_input": {"command": command, "description": "experiment trigger"}})
    elif event == "UserPromptSubmit":
        base["prompt"] = "Run this exact shell command and nothing else: %s" % command
    elif event == "Stop":
        base["stop_hook_active"] = stop_hook_active
    return base


def _gate(config_path, event, payload, *, cwd, timeout):
    """Run every hook wired at `event`; stop at the first that does not allow."""
    state = {
        "decision": ALLOW,
        "reason": "no hook wired",
        "updated": None,
        "invoked": False,
        "exit": None,
        "timed_out": False,
    }
    blob = json.dumps(payload).encode("utf-8")
    for hook_command in _hook_commands(config_path, event):
        state["invoked"] = True
        try:
            proc = subprocess.run(  # noqa: S602 - the command under test is ours, in a scratch dir
                hook_command,
                shell=True,
                input=blob,
                capture_output=True,
                cwd=cwd,
                timeout=timeout if timeout is not None else CLAUDE_CODE_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired:
            state.update({"timed_out": True, "reason": "hook timed out, non-blocking", "exit": None})
            return state
        state["exit"] = proc.returncode
        proc.stdout = proc.stdout.decode("utf-8", "replace")
        proc.stderr = proc.stderr.decode("utf-8", "replace")
        decision, reason, updated = _interpret(proc, GRAMMARS.get(event, "G2"))
        state.update({"decision": decision, "reason": reason})
        if updated and isinstance(updated, dict) and updated.get("command"):
            state["updated"] = updated["command"]
        if decision != ALLOW:
            return state
    return state


def run_turn(config_path, *, command, cwd, session_id="reference-run", timeout=None, max_continuations=1):
    """One whole turn: prompt gate, tool gate, stop gate -- with the trigger in the middle.

    A blocked Stop means the agent does *not* finish, so it comes back round and runs the
    tool again. That second run is how a Stop-gate block becomes observable at all: the
    trigger appends, so the harness reads "how many times did the action happen".
    """
    gates, runs, continuations = {}, 0, 0
    while True:
        prompt = _gate(
            config_path,
            "UserPromptSubmit",
            _payload("UserPromptSubmit", cwd=cwd, command=command, session_id=session_id),
            cwd=cwd,
            timeout=timeout,
        )
        gates.setdefault("UserPromptSubmit", prompt)
        if prompt["decision"] != ALLOW:
            break

        pre = _gate(
            config_path,
            "PreToolUse",
            _payload("PreToolUse", cwd=cwd, command=command, session_id=session_id),
            cwd=cwd,
            timeout=timeout,
        )
        gates.setdefault("PreToolUse", pre)
        if pre["decision"] == ALLOW:
            subprocess.run(pre["updated"] or command, shell=True, cwd=cwd, capture_output=True)  # noqa: S602
            runs += 1

        stop = _gate(
            config_path,
            "Stop",
            _payload("Stop", cwd=cwd, command=command, session_id=session_id, stop_hook_active=continuations > 0),
            cwd=cwd,
            timeout=timeout,
        )
        gates.setdefault("Stop", stop)
        if stop["decision"] == ALLOW or continuations >= max_continuations:
            break
        continuations += 1

    return {
        "gates": {k: {kk: vv for kk, vv in v.items() if kk != "updated"} for k, v in gates.items()},
        "action_runs": runs,
        "continuations": continuations,
        "action_ran": runs > 0,
    }


def run_pre_tool(config_path, *, command, cwd, session_id="reference-run", timeout=None):
    """One PreToolUse gate in isolation, for experiments scoped to that event."""
    state = _gate(
        config_path,
        "PreToolUse",
        _payload("PreToolUse", cwd=cwd, command=command, session_id=session_id),
        cwd=cwd,
        timeout=timeout,
    )
    ran = False
    if state["decision"] == ALLOW:
        subprocess.run(state["updated"] or command, shell=True, cwd=cwd, capture_output=True)  # noqa: S602
        ran = True
    return {
        "decision": state["decision"],
        "reason": state["reason"],
        "hook_invoked": state["invoked"],
        "hook_exit": state["exit"],
        "hook_timed_out": state["timed_out"],
        "action_ran": ran,
        "effective_command": (state["updated"] or command) if ran else None,
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 3:  # noqa: PLR2004
        sys.stderr.write("usage: reference_agent.py <settings.json> <cwd> <command>\n")
        return 2
    sys.stdout.write(json.dumps(run_turn(argv[0], command=argv[2], cwd=argv[1]), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
