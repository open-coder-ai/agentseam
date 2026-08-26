# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- Detection collision: Codex CLI claimed any payload carrying `model`, which Cursor's base
  hook schema sends on every event — so every real Cursor payload was ambiguous between
  the two adapters, and an unidentified payload is allowed through. Codex now claims only
  on `turn_id`/`permission_mode`, and Cursor requires one of its own base-schema fields on
  the event names it shares with Codex.
- Devin reuses Claude Code's event vocabulary; `claude_code.claims()` no longer claims a
  payload carrying Devin's `prompt_id`.
- Cursor `preToolUse` nests the target in `tool_input`, so `Event.path` was `None` on
  exactly the gate that can still stop a write.
- Cursor degradation messages replaced the handler's own reason instead of adding to it.

### Added
- Canonical 12-event lifecycle vocabulary, normalized `Event`, and `Decision`
  (allow / deny / ask / rewrite).
- Capability matrix as data, with per-row verification provenance and honest
  enforcement levels (enforced / best-effort / detect / none).
- Adapters: Claude Code, Cursor, GitHub Copilot (VS Code agent mode / CLI), Gemini CLI,
  OpenAI Codex CLI, Windsurf.
- Complete agent coverage: 15 agents in the capability matrix, every one also reachable
  by instruction files. New `unadapted` tier distinguishes 'we have no adapter' from
  'this agent exposes no hooks'.
- Dispatcher with honest degradation: a `rewrite` on an agent that cannot rewrite
  becomes `ask`, never a silent pass-through.
- Idempotent, ownership-marked hook installation; surgical uninstall.
- CLI: `agents`, `matrix`, `doctor`, `install`, `uninstall`.
- Instruction files (primitive 2): the 14-agent map, `plan`/`write`/`remove`/`discover`,
  and an `instructions` CLI command. Writes a marker-delimited managed block so
  human-authored content is never clobbered, and prefers the shared AGENTS.md over
  per-agent copies.
- Permission config (primitive 4): per-agent config-file map with precedence, a
  capability model recording which of allow/ask/deny each agent's config can actually
  express, capability-based `Rule`s, and per-agent renderers. `plan()` returns both the
  native fragment and every rule the agent has no faithful way to state, so a policy can
  never silently render into something weaker; `agentseam permissions` exits non-zero
  when a rule would not have been enforced.
- Packaging (primitive 3): per-agent bundle layouts, a `Bundle`/`Part` model, and
  `plan()` rendering a bundle into the exact files each agent expects. `same_path_for()`
  reports the parts whose path is identical across formats (skills, subagents and hooks
  are byte-identical between a Claude Code plugin and a Gemini CLI extension; commands
  are not), and `also_reads()` records the folders one agent reads from another's layout.
- Cursor: full hook surface from vendor documentation. `preToolUse` is generic (every
  tool, not just shell) and carries `updated_input`, so Cursor is now block+rewrite
  including on file writes; `beforeReadFile`, `postToolUseFailure`, subagent and Tab
  events added. `hook_config()` sets `failClosed: true` on every gate it installs.
- Devin CLI adapter: block, rewrite and context injection over its Claude Code-compatible
  hook format, writing `.devin/hooks.v1.json`.
- New `enforceable` enforcement level and `FAIL_CONFIGURABLE` fail mode, for a surface
  that fails open by default but can be told to fail closed.
- Examples: cross-agent event log, cross-agent notifier.

[Unreleased]: https://github.com/open-coder-ai/agentseam/commits/main
