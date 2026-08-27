"""The caveats each matrix row carries, kept apart from the capabilities it declares.

Two different activities. A row's `events` table is a set of capability tuples that a
consumer queries; its note is prose telling a human what to watch out for -- which surface
is missing, which decision word the vendor accepts but does not honour, what fails open.
The prose is the part that grows, and it grows every time a vendor is read properly.
"""

from __future__ import annotations

NOTES = {
    "junie": "Strongest gate here: PreToolUse returns allow/ask/block and carries "
    "updatedInput, so block, ask and rewrite are all native. Its event names and field "
    "names are Claude Code's by design; project_path is what separates the two payloads. "
    "Project-local hooks in <project>/.junie/config.json are IGNORED by default for "
    "safety, so a guardrail committed to a repo does not run for a teammate who clones it "
    "-- the user file is the only location that takes effect without --config-location. "
    "PermissionRequest inverts the usual default: a hook exiting 0 without a blocking "
    "decision approves the action and skips the dialog the user would have seen. Deliberately "
    "not installable on its own -- it shares canonical pre_tool with PreToolUse, and "
    "install('junie', ['pre_tool']) wires only PreToolUse, since bundling the two would hand "
    "a consumer an approve-by-default gate they did not ask for. Wire it by hand if wanted. "
    "StopFailure is observability-only and fires on LLM/API failures, not tool failures, "
    "so it is not tool_failure and is left unmapped. Non-zero exits other than 2 are "
    "warnings and execution proceeds, so this fails OPEN.",
    "tabnine": "Eleven events, six of which can block -- including AfterTool, which most "
    "agents treat as observation only. Event names are Gemini CLI's exactly; the only "
    "documented separator is `timestamp` in Tabnine's base schema, which identifies "
    "Tabnine but cannot exclude Gemini, so detect() declines these payloads and the agent "
    "must be named explicitly. Fails OPEN unusually broadly: any exit code other than 0 "
    "or 2 proceeds, AND stdout that is not valid JSON is treated as a systemMessage and "
    "the action is ALLOWED -- so a chatty or crashed hook is a permitted action. Rewrite "
    "is advertised in the vendor overview but the field carrying it was not in the "
    "documentation read here, so no rewrite is claimed.",
    "replit": "No hook surface found in the vendor documentation. Recorded as not-found "
    "rather than absent: this is a hosted agent, and the search was of published docs, not "
    "of a running instance. Instruction files still reach it.",
    "antigravity": "Richest decision vocabulary here -- allow, deny, ask, force_ask and deny_unless_prior_grant -- but no rewrite, since permissionOverrides widens permissions rather than changing arguments. The payload carries NO event name, so the event is inferred from shape, and PreToolUse/PostToolUse differ only by an `error` field documented as empty rather than absent; ties go to PreToolUse because the opposite guess would skip the gate. PreInvocation and PostInvocation have identical payloads and are unmapped. Fail mode is not documented, so the weaker claim (open) is recorded rather than a guess in our own favour.",
    "claude_code": "Richest surface (~30 events). Blocks via exit 2 or hookSpecificOutput.permissionDecision; rewrite via updatedInput (pre_tool only). Live capture 2026-08-27 found detection broken against current builds: Claude Code now sends prompt_id, which this adapter treated as proof a payload was Devin's, so 38 of 42 real payloads were claimed by Devin instead and a deny rendered in the wrong dialect. Fixed by discriminating on fields observed from Claude Code rather than on a field it was assumed to lack.",
    "codex_cli": "Claude-family decision shape (hookSpecificOutput.permissionDecision) but camelCase event names and extra turn-scoped fields (turn_id, permission_mode -- and model, which Cursor also sends and therefore cannot discriminate). Deny is sent as JSON with exit 0: on Windows Codex wraps hooks in powershell -Command, which collapses exit 2 into 1, so an exit-code deny does not survive that platform.",
    "cursor": "Fails OPEN by default; failClosed:true per hook definition makes it fail closed, and agentseam sets it on every gate it installs. `ask` is accepted by the preToolUse schema but not enforced today, so the adapter denies instead of returning a prompt that would behave as a pass; beforeShellExecution and beforeMCPExecution do honour ask. Separate Tab hooks (beforeTabFileRead, afterTabFileEdit) gate inline completions, and workspaceOpen fires outside any session with no canonical event here. Cursor also loads Claude Code-format hooks -- confirmed live (2026-08-27): with both `.cursor/hooks.json` and `.claude/settings.json` carrying the same probe, every event fired twice, once per config. Witnessed live (Windows, 2026-08-27): a beforeShellExecution hook that produced no stdout caused the tool call to be REJECTED -- an empty response is not an allow, so silence blocks and the documented fail-open covers something narrower than any-hook-problem. A hook wired here must answer in-dialect. Across three capture sessions in which shell commands ran, beforeShellExecution never fired while tool_input.command arrived under preToolUse instead -- non-observation, not evidence of absence, but enough that a consumer should gate shell on pre_tool rather than assume the dedicated event.",
    "devin": 'Speaks Claude Code\'s hook format almost exactly, and reads .claude/settings.json for hooks by default -- so a repo with Claude Code hooks is already running them under Devin. A block is top-level {"decision": "block"}, not permissionDecision. There is no ask in the vocabulary. Non-zero exit codes other than 2 are logged without blocking, so this fails OPEN. A SessionStart payload is indistinguishable from Claude Code\'s, and detect() refuses to guess between them.',
    "gemini_cli": "Top-level `decision: allow|deny` + `reason` (not nested); rewrite merges via hookSpecificOutput.tool_input; exit 2 also blocks. Write tools are write_file/replace. Fail mode is not documented as closed, so pre_tool is rated best-effort rather than enforced.",
    "grok": "PreToolUse is the ONLY blocking event; everywhere else stdout is ignored. No rewrite: the vocabulary is {decision: deny, reason} and nothing more. Fails OPEN -- timeouts, crashes and malformed output are recorded and the call proceeds. Payload fields are camelCase (hookEventName, toolName) while event values stay PascalCase, which is what separates it from Claude Code, Codex and VS Code Copilot. Reads .claude/settings.json and .cursor/hooks.json too. Project hooks need trust (/hooks-trust or --trust) before they run, so a written config is not yet a live one.",
    "kimi_code": "Twenty events, of which exactly three block: PreToolUse, UserPromptSubmit and Stop. The rest are documented as fire-and-forget, so a decision returned there changes nothing. Accepts Claude Code's hookSpecificOutput.permissionDecision shape, and exit 2 blocks too -- but the JSON form carries the reason back into the model's context. No rewrite. Config is TOML ([[hooks]] in config.toml, four fields only; a fifth makes the whole file fail to load), so installation appends a marker-delimited block rather than rewriting the user's settings. Fails OPEN, and the vendor says outright that hooks here are not a sole security barrier. Only client_type separates its payloads from Claude Code's.",
    "vscode_copilot": "Same PreToolUse contract as Claude Code (permissionDecision/updatedInput) and parses Claude settings.json via hookClaudeCompat. Memory writes arrive as the 'memory' tool (create/str_replace/insert), not file edits.",
    "windsurf": "Exit code 2 is the ONLY block signal: no stdout decision protocol, no machine-readable reason, no rewrite. Critically there is NO file-write event -- prompt, terminal and MCP hooks only -- so a write to a memory file is invisible to a hook on this agent. Fail mode is undocumented, so blocking rates best-effort rather than enforced.",
}
