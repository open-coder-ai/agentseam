# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- Examples: cross-agent event log, cross-agent notifier.

[Unreleased]: https://github.com/open-coder-ai/agentseam/commits/main
