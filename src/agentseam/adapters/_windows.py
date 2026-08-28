"""PowerShell's one rule that breaks hook commands, shared by the vendors it affects.

Two adapters here need this and for the same reason, so the explanation lives once rather
than twice: a copy that drifts is how a vendor fact becomes two disagreeing vendor facts.
"""

from __future__ import annotations


def powershell_command(command):
    """`command` rewritten so PowerShell will actually run it.

    A command line that BEGINS with a quoted path is parsed by PowerShell as a string
    expression, not an invocation -- and a bare string followed by more arguments is a
    parse error, so nothing runs at all. `&` is PowerShell's call operator, and it makes a
    quoted path executable.

    Witnessed live (Codex CLI 0.150.1, Windows, 2026-08-28): the quoted form failed with
    "hook exited with code 1" on every event, and a `> file 2>&1` redirect appended to it
    produced NO file -- proof the line never reached execution, since PowerShell sets up
    redirection only for a command it could parse. Prefixing `&` ran the hook immediately.
    A bare `python3 "..."` also works, because it parses in command mode; the difference is
    the leading quote, not the interpreter.

    Both vendors route hooks through PowerShell on Windows. Codex wraps them itself;
    VS Code Copilot does it in hookExecutor.ts's getShellCommand, which spawns
    `powershell.exe -ExecutionPolicy Bypass -NoProfile -NoLogo -Command <hookCommand>`
    whenever ComSpec is cmd.exe -- i.e. by default. Each adapter passes the result through
    its own per-platform override field, so the POSIX `command` keeps the exact quoted
    interpreter path that installed the hook.
    """
    return command if command.lstrip().startswith("&") else "& " + command
