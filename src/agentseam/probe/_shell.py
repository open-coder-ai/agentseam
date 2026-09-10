"""The one place this package hands a command string to a shell.

`agentseam-no-shell-true` bans `shell=True` across `src/`, and it is right to: the runtime
path sits inline in a developer's agent loop, on payloads an attacker can influence. The
probe is not that path. It is a deliberate command-runner, and the shell is the thing under
measurement rather than an implementation detail:

- `reference_agent` is Claude Code's protocol made executable, and Claude Code runs a hook by
  handing a command string to a shell. An argv list would emulate a vendor that does not
  exist, and every `tested`-basis row is measured against this driver.
- The `transform` trial runs the command *as the hook rewrote it*. Measuring the rewrite means
  running the rewrite.
- The driver template is a command line the operator typed on their own machine.

So the exception is real, and it is confined to this function rather than scattered across four
call sites: one place to audit, and the rule keeps biting everywhere else in `src/`.
"""

from __future__ import annotations

import subprocess


def run_shell(command, *, check=False, capture_output=True, **kwargs):
    """`subprocess.run(command, shell=True)`, defaulted to capture and never to raise."""
    # nosemgrep: agentseam-no-shell-true -- the audited exception; see this module's docstring.
    return subprocess.run(  # noqa: S602
        command, shell=True, check=check, capture_output=capture_output, **kwargs
    )
