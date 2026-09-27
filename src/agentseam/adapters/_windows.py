"""PowerShell's one rule that breaks hook commands, shared by the vendors it affects."""

from __future__ import annotations

#: `pwsh -Command` exits 1 whenever the last native command failed, whatever its code, so a
#: hook's exit 2 (block) reached the host as 1 (a non-blocking error): openai/codex#48183.
#: When no native command ran at all (the interpreter is not on PATH), $LASTEXITCODE is $null
#: and `exit $null` is 0 -- an allow; nothing judged the call, so that refuses (2) instead.
_KEEP_EXIT = "; if ($null -eq $LASTEXITCODE) { exit 2 }; exit $LASTEXITCODE"

#: The suffix before the $null guard; an entry carrying it is upgraded, not suffixed twice.
_BARE_EXIT = "; exit $LASTEXITCODE"


def powershell_command(command):
    """`command` rewritten so PowerShell will actually run it and keep its exit code."""
    body = command if command.lstrip().startswith("&") else "& " + command
    body = body.rstrip()
    if body.endswith(_KEEP_EXIT):
        return body
    if body.endswith(_BARE_EXIT):
        body = body[: -len(_BARE_EXIT)]
    return body + _KEEP_EXIT
