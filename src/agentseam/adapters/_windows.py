"""PowerShell's one rule that breaks hook commands, shared by the vendors it affects."""

from __future__ import annotations

#: `pwsh -Command` exits 1 whenever the last native command failed, whatever its code, so a
#: hook's exit 2 (block) reached the host as 1 (a non-blocking error): openai/codex#48183.
_KEEP_EXIT = "; exit $LASTEXITCODE"


def powershell_command(command):
    """`command` rewritten so PowerShell will actually run it and keep its exit code."""
    body = command if command.lstrip().startswith("&") else "& " + command
    return body if body.rstrip().endswith(_KEEP_EXIT) else body + _KEEP_EXIT
