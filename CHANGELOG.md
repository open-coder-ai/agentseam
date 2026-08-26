# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- VS Code Copilot's adapter told itself apart from Cursor only by fields belonging to
  Cursor's schema, and rested on `model` in particular — so a Cursor payload without it
  was claimed by both, which makes detection ambiguous and lets the dispatcher allow what
  it was gating. Found while writing the vendor examples, whose scenario omitted the
  field. Each vendor now has several markers rather than one.
- Primitives 3 and 4 knew nothing about nine agents the matrix knows, including four that
  had gained hook adapters since those modules were written. They were absent from both
  the recorded and the unrecorded tables, which reads as "nothing to say here" when the
  truth is "nobody looked" — the exact failure those modules exist to prevent. Both tables
  are now exhaustive, and a test asserts recorded + unrecorded == the matrix, so an agent
  joining the matrix fails until somebody records what its config and packaging can do.
- Gemini CLI claimed any payload whose event name it recognised, including `SessionStart`
  — which Claude Code, Devin and Kimi Code all spell the same way. A Kimi payload was
  therefore claimed by two adapters at once. Adapters now decline a payload that names a
  different client: a positive self-identification beats a shared event name.
- Adapters explaining a degraded outcome read `Decision.evidence["degraded_from"]` rather
  than the outcome they were handed, via a new `contract.degraded_from()`. A rewrite that
  the dispatcher reduced to `ask`, then blocked by an agent that cannot prompt, was being
  reported as a failed confirmation request — and it was never a confirmation request.
  Affected Cursor, Devin, Grok and Antigravity.
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
- Grok CLI adapter: block on PreToolUse (its only blocking event), fail-open, no rewrite.
  Detected by its unique pairing of a camelCase `hookEventName` key with PascalCase values.
- Antigravity adapter: block on PreToolUse and refusal-to-stop on Stop. Its payload carries
  no event name at all, so the event is inferred from shape, with ties broken toward the
  gate.
- Kimi Code CLI adapter: block on PreToolUse, UserPromptSubmit and Stop — the only three
  of its twenty events whose return value reaches the main flow. Fail-open, no rewrite.
- TOML config support in `install`: a marker-delimited block appended to the user's
  settings file, with every byte outside it preserved. Kimi Code's `[[hooks]]` live in
  `config.toml` alongside everything else the user configures.
- Generated vendor examples: `examples/generated/` has a page per adapted agent showing
  the same situation — an agent about to write a secret into a file it reads back — in
  that vendor's dialect: the config `install` writes, the normalized event, and every
  decision on the way back including the ones reduced because the agent cannot express
  them. Produced by `examples/generate.py` from the real code paths, with a test and a CI
  job that fail on drift.
- Examples: cross-agent event log, cross-agent notifier.

[Unreleased]: https://github.com/open-coder-ai/agentseam/commits/main
