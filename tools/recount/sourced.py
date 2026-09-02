"""Primary-sourced additions folded over the recount (the post-C2 data gaps, chock#97).

Stated tables like `tables.py`'s, each value carrying its citation; the consistency test
replays them and `tests/test_vendor_config.py` pins the pairing rules.
"""

from __future__ import annotations

#: The vendor's own token for the repository/project root, usable inside a hook command.
#: claude_code: code.claude.com/docs/en/hooks ("Reference scripts by path", read
#: 2026-09-01) -- ${CLAUDE_PROJECT_DIR} is "the project root where the session started",
#: set in the hook command's environment. No other vendor's primary source read here
#: documents such a token for its hooks surface, so no other entry carries the key.
REPO_ROOT_TOKEN = {"claude_code": "${CLAUDE_PROJECT_DIR}"}

#: Per-claim evidence records that differ from `tables.evidence`'s default (the matrix
#: row's own verified basis/date, tested by the recount consistency test).
#: - vscode_copilot tools: the shell vocabulary is the vendor's hooks reference
#:   (docs.github.com/en/copilot/reference/hooks-reference, "Tool names for hook
#:   matching", read 2026-09-01): runtime names bash/powershell, spoken as Claude's Bash
#:   in PascalCase payloads. Corroborated, not established, by chock's live witness of
#:   2026-08-23 (third-party install, exit-2 deny on Copilot CLI and VS Code agent mode):
#:   its matcher was an alternation, and an alternation firing does not establish each
#:   token, so the pwsh/sh/shell tokens it also carried are NOT recorded here.
#: - codex_cli tools: the matrix row's own live capture (2026-08-28, 36 payloads:
#:   "Codex sends exactly two tool names, Bash and apply_patch"); the date and basis are
#:   that row's, the test the one that pins the recorded vocabulary.
EVIDENCE = {
    ("vscode_copilot", "tools"): {
        "basis": "vendor-docs",
        "date": "2026-09-01",
        "test": "tests/test_vendor_lookups.py::test_shell_tools_are_recorded_only_where_established",
    },
    ("codex_cli", "tools"): {
        "basis": "live-run-partial",
        "date": "2026-08-28",
        "test": "tests/test_vendor_lookups.py::test_shell_tools_are_recorded_only_where_established",
    },
    ("claude_code", "repo_root_token"): {
        "basis": "vendor-docs",
        "date": "2026-09-01",
        "test": "tests/test_vendor_config.py::test_repo_root_token_is_recorded_only_where_primary_sourced",
    },
}


def apply(agent, entry):
    """Fold this module's sourced records into one recounted entry, in place."""
    if agent in REPO_ROOT_TOKEN:
        entry["repo_root_token"] = REPO_ROOT_TOKEN[agent]
    for (owner, claim), record in EVIDENCE.items():
        if owner == agent:
            entry["evidence"][claim] = dict(record)
    return entry
