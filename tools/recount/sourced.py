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

#: Other agents' repo hook configs this agent also loads and runs. grok:
#: docs.x.ai/build/features/hooks (read 2026-10-13) -- "Claude Code (.claude/settings.json)
#: and Cursor (.cursor/hooks.json) hook files are read as well"; xai-org/grok-build@2bdd1d6
#: crates/codegen/xai-grok-hooks/src/discovery.rs:386-398 adds .claude/settings.local.json,
#: and user-guide/10-hooks.md:77 says these are scanned by default. Its dedup key is
#: (event, command, url, matcher) (discovery.rs:233), so only an identical hook runs once.
ALSO_READS = {"grok": [".claude/settings.json", ".claude/settings.local.json", ".cursor/hooks.json"]}

#: Project hooks that run only once the user trusts them, and how the user does that.
#: codex_cli: learn.chatgpt.com/docs/hooks (read 2026-09-27) -- "Project-local hooks load
#: only when the project `.codex/` layer is trusted"; `/hooks` reviews and trusts them, and
#: trust is recorded against the hook's hash, so a changed hook is skipped until re-trusted.
#: cline: .clinerules/hooks/README.md in cline/cline ("Enabling Hooks": open Cline settings, Feature
#: Settings, check "Enable Hooks"; read 2026-10-11) and cline.bot/blog/cline-v3-36-hooks ("macOS and
#: Linux only").
TRUST_HINT = {
    "cline": "in the VS Code extension, tick Enable Hooks under Cline's Feature settings; hooks run on macOS and Linux only",
    "codex_cli": "run /hooks in Codex and trust the new hook (trust is per hook hash: re-trust after any change)",
}

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
#: - cursor tools: the row's live witness of 2026-09-23 (3.21.18, Windows): `Write` at the
#:   generic preToolUse gate, carrying file_path and the full content, for a new file and for
#:   an edit alike; the only write tool seen, and a deny against it was honoured.
#: - vscode_copilot fields: the Copilot CLI camelCase chains (toolArgs, sessionId,
#:   toolResult.textResultForLlm) are the vendor's hooks reference
#:   (docs.github.com/en/copilot/reference/hooks-configuration, read 2026-09-27); no live
#:   capture of that shape exists, so the claim now rests on the docs, not the live run.
#: - claude_code tools: the write tools and Bash are the row's live run (2026-09-07);
#:   PowerShell is the vendor's tools reference (code.claude.com/docs/en/tools-reference,
#:   read 2026-09-27: on by default on Windows, "receive the tool's command string in
#:   tool_input.command, with the same fields as the Bash tool"; match `Bash|PowerShell`),
#:   not yet seen live, so the claim as a whole now rests on the docs.
#: - claude_code fields: the output chain is the vendor's hooks reference
#:   (code.claude.com/docs/en/hooks, read 2026-10-13): PostToolUse carries `tool_response`,
#:   PostToolUseFailure carries `error`. No live capture covers either event, and the
#:   `tool_output` the chain read alone before is attested by no source.
#: - devin fields: the output chain is the vendor's lifecycle-hooks reference
#:   (docs.devin.ai/cli/extensibility/hooks/lifecycle-hooks, PostToolUse, read 2026-10-13):
#:   `tool_response` is an object with `success`, `output` and `error` (string or null). The
#:   `tool_output` the chain read before is attested by no Devin source, and no live run covers it.
#: - grok hook_entry: the wrapper is the row's docs read (2026-08-26); also_wires PermissionDenied is
#:   docs.x.ai/build/features/hooks (read 2026-10-13: "The permission system denies a tool call").
#: - grok claims: the twin-key self-identification is the vendor's source, xai-org/grok-build@2bdd1d6
#:   (crates/codegen/xai-grok-hooks/src/event.rs, to_hook_json writes hook_event_name beside the
#:   camelCase hookEventName for every event), read 2026-10-13.
#: - claude_code hook_entry: the wrapper is the row's live run (2026-09-07); watch_list_events is
#:   the vendor's hooks reference (code.claude.com/docs/en/hooks, FileChanged, read 2026-10-13),
#:   not yet seen live, so the claim as a whole now rests on the docs.
EVIDENCE = {
    ("grok", "hook_entry"): {
        "basis": "vendor-docs",
        "date": "2026-10-13",
        "test": "tests/test_adapter_grok.py::test_tool_failure_also_wires_permission_denied",
    },
    ("grok", "claims"): {
        "basis": "vendor-source",
        "date": "2026-10-13",
        "test": "tests/test_adapter_grok.py::test_a_new_grok_event_is_claimed_and_parsed_as_unknown",
    },
    ("devin", "fields"): {
        "basis": "vendor-docs",
        "date": "2026-10-13",
        "test": "tests/test_adapter_devin.py::test_post_tool_output_is_read_from_the_documented_tool_response",
    },
    ("claude_code", "hook_entry"): {
        "basis": "vendor-docs",
        "date": "2026-10-13",
        "test": "tests/test_install_watch.py::test_file_changed_is_not_wired_without_a_watch_list",
    },
    ("claude_code", "fields"): {
        "basis": "vendor-docs",
        "date": "2026-10-13",
        "test": "tests/test_adapter_claude_code.py::test_post_tool_output_is_read_from_the_documented_tool_response",
    },
    ("cline", "trust_hint"): {
        "basis": "vendor-docs",
        "date": "2026-10-11",
        "test": "tests/test_adapter_cline.py::test_install_names_the_settings_switch",
    },
    ("codex_cli", "trust_hint"): {
        "basis": "vendor-docs",
        "date": "2026-09-27",
        "test": "tests/test_cli.py::test_install_says_how_to_trust_a_hook_the_agent_will_not_run_yet",
    },
    ("claude_code", "tools"): {
        "basis": "vendor-docs",
        "date": "2026-09-27",
        "test": "tests/test_adapter_claude_code.py::test_powershell_is_a_shell_tool_and_its_command_is_parsed",
    },
    ("vscode_copilot", "fields"): {
        "basis": "vendor-docs",
        "date": "2026-09-27",
        "test": "tests/test_adapter_vscode_copilot.py::test_copilot_cli_tool_args_reach_the_policy_as_object_or_json_text",
    },
    ("cursor", "tools"): {
        "basis": "live-run-partial",
        "date": "2026-09-23",
        "test": "tests/test_vendor_lookups.py::test_cursor_write_tools_are_recorded_from_the_live_witness",
    },
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
    ("tabnine", "verdicts"): {
        "basis": "vendor-docs",
        "date": "2026-10-13",
        "test": "tests/test_vendor_config.py::test_no_vendor_vocabulary_is_left_unverified",
    },
    ("windsurf", "claims"): {
        "basis": "vendor-docs",
        "date": "2026-10-13",
        "test": "tests/test_adapter_windsurf.py::test_the_documented_payloads_parse_by_their_named_event",
    },
    ("windsurf", "fields"): {
        "basis": "vendor-docs",
        "date": "2026-10-13",
        "test": "tests/test_adapter_windsurf.py::test_the_documented_payloads_parse_by_their_named_event",
    },
    ("grok", "also_reads"): {
        "basis": "vendor-source",
        "date": "2026-10-13",
        "test": "tests/test_doctor_compat.py::test_doctor_names_a_compat_file_grok_also_runs",
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
    if agent in ALSO_READS:
        entry["also_reads"] = list(ALSO_READS[agent])
    if agent in TRUST_HINT:
        entry["needs_trust"] = True
        entry["trust_hint"] = TRUST_HINT[agent]
    for (owner, claim), record in EVIDENCE.items():
        if owner == agent:
            entry["evidence"][claim] = dict(record)
    return entry
