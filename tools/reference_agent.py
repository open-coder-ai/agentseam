#!/usr/bin/env python3
"""A coding agent that behaves exactly as its vendor documentation says it does.

This is not a mock in the testing sense -- it is the documentation, made executable. It
reads the same config file the real agent reads, invokes the hook the same way, and
interprets the answer by the letter of the published protocol.

Two things fall out of that:

1. **The harness is testable with no credentials, no network, and no vendor account.**
   Every part of tools/experiment.py can be exercised in CI for free.
2. **`vendor-docs` becomes a measurable position rather than a guess.** Run the harness
   against this agent and against the real one; where they disagree, the documentation is
   wrong. That delta is the finding -- and it is exactly the class of thing
   matrix-evidence.json currently has no way to record.

Only the documented path is implemented. Where the docs are silent this raises rather
than guessing, because a guess here would launder itself into evidence.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

#: Claude Code's PreToolUse contract, from its hooks reference. Exit codes first: they
#: take precedence over stdout in the published order of evaluation.
CLAUDE_CODE_TIMEOUT_SECONDS = 60

ALLOW, DENY, ASK = "allow", "deny", "ask"


class Undocumented(Exception):
    """The protocol does not say what happens here, so the reference will not invent it."""


def _hook_commands(config_path, event="PreToolUse"):
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


def _interpret_claude_code(proc):
    """(decision, reason, updated_input) from one hook process, per the documented rules."""
    # Exit 2 is the blocking error: stderr is fed back as the reason.
    if proc.returncode == 2:  # noqa: PLR2004
        return DENY, (proc.stderr or "").strip() or "blocked by hook", None

    # Any other non-zero is a *non-blocking* error: surfaced to the user, action proceeds.
    # This is the documented fail-open, and the single most consequential line in the
    # protocol -- it is what the `crash` trial measures.
    if proc.returncode != 0:
        return ALLOW, "hook error (exit %d), non-blocking" % proc.returncode, None

    text = (proc.stdout or "").strip()
    if not text:
        # Documented: exit 0 with no stdout is success, and success means proceed.
        return ALLOW, "silent success", None

    try:
        body = json.loads(text)
    except ValueError:
        # Documented: non-JSON stdout on exit 0 is transcript context, not a verdict.
        return ALLOW, "non-JSON stdout treated as context", None

    specific = body.get("hookSpecificOutput") or {}
    updated = specific.get("updatedInput")
    decision = specific.get("permissionDecision")
    if decision in (ALLOW, DENY, ASK):
        return decision, specific.get("permissionDecisionReason") or "", updated
    if decision is not None:
        raise Undocumented("unrecognised permissionDecision: %r" % (decision,))

    # The older top-level form, still honoured.
    if body.get("decision") == "block":
        return DENY, body.get("reason") or "blocked by hook", None
    if body.get("continue") is False:
        return DENY, body.get("stopReason") or "stopped by hook", None
    return ALLOW, "no decision field", updated


def run_pre_tool(config_path, *, command, cwd, session_id="reference-run", timeout=None):
    """Simulate one PreToolUse gate around a Bash command. Returns a result dict.

    The command is executed only if the gate permits it -- the sentinel it writes is how
    the harness observes the outcome without parsing anyone's dialect.
    """
    payload = {
        "session_id": session_id,
        "transcript_path": os.path.join(cwd, "transcript.jsonl"),
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": command, "description": "experiment trigger"},
    }
    blob = json.dumps(payload).encode("utf-8")

    decision, reason, invoked, exit_code, timed_out = ALLOW, "no hook wired", False, None, False
    effective = command
    for hook_command in _hook_commands(config_path):
        invoked = True
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
            # Documented as a non-blocking error for that hook: the agent proceeds.
            timed_out = True
            decision, reason, exit_code = ALLOW, "hook timed out, non-blocking", None
            break
        exit_code = proc.returncode
        proc.stdout = proc.stdout.decode("utf-8", "replace")
        proc.stderr = proc.stderr.decode("utf-8", "replace")
        decision, reason, updated = _interpret_claude_code(proc)
        # Documented: updatedInput replaces the tool input the agent then executes.
        if updated and isinstance(updated, dict) and updated.get("command"):
            effective = updated["command"]
        if decision != ALLOW:
            break

    ran = False
    if decision == ALLOW:
        subprocess.run(effective, shell=True, cwd=cwd, capture_output=True)  # noqa: S602
        ran = True

    return {
        "decision": decision,
        "reason": reason,
        "hook_invoked": invoked,
        "hook_exit": exit_code,
        "hook_timed_out": timed_out,
        "action_ran": ran,
        "effective_command": effective if ran else None,
    }


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 3:  # noqa: PLR2004
        sys.stderr.write("usage: reference_agent.py <settings.json> <cwd> <command>\n")
        return 2
    result = run_pre_tool(argv[0], command=argv[2], cwd=argv[1])
    sys.stdout.write(json.dumps(result, indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
