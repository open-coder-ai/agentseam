"""PowerShell's one rule that breaks hook commands, shared by the vendors it affects."""

from __future__ import annotations


def powershell_command(command):
    """`command` rewritten so PowerShell will actually run it."""
    return command if command.lstrip().startswith("&") else "& " + command
