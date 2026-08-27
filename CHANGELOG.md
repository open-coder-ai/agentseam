# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `live-run-partial`, a sixth `verified.basis` value, and an `observed` list on the evidence
  record naming the canonical events actually seen fire. Cursor's row is the first to use
  both: 120 real payloads across four capture sessions on Cursor 3.17.8 observed 6 of the 11
  events it claims. Neither existing word was true -- `vendor-docs` would understate a row
  somebody really ran, and `live-run` would let a consumer filtering for observed rows rely
  on a gate nobody has seen fire. The same reasoning that produced `enforceable`.
  `matrix.observed(agent)` exposes the list; three invariants keep it honest (a partial row
  must name events, may only name events the row claims, and may not be missing none).
- The capture report states the agent version it observed. Redaction already let it through
  -- `cursor_version` is on the structural allowlist and a version string is enum-like -- but
  the report printed only key *paths*, so the one fact a `verified` matrix record requires
  sat in the capture file unread and was asked for by hand three sessions running.
- `capture.py conflicts` names every config in a repo that fires the probe, and exits
  non-zero when more than one does. `install` warns about the same thing while it is still
  cheap to act on.

### Fixed
- The report called an unlabelled payload "No adapter for this agent yet", which reads as a
  thirteenth vendor when it is a labelling miss. Witnessed live: 27 payloads labelled
  `cursor` beside 26 labelled `?`, near 1:1 -- because Cursor also loads Claude Code-format
  hooks, so a leftover `.claude/settings.json` entry fired the same probe on the same events
  without the agent argument. The report now says so and points at `conflicts`.
- Concurrent probes tore records in half. Cursor runs subagents in parallel -- its payloads
  carry `is_parallel_worker`, `subagent_id` and a `subagentStart` event -- so several probe
  processes appended to one capture file at once and their buffered writes interleaved.
  Witnessed live: two records split mid-string, and `report` crashed on the first fragment,
  taking 122 good records with it. Each probe now writes its own `captured.<pid>.jsonl` with
  a single `os.write()`, and the loader reads every shard, skips any line that is not whole,
  and reports how many it skipped rather than presenting a partial capture as a complete one.
  (The entry above shipped in #24 describing code that did not: the commit carried only the
  changelog and the runbook. The code landed in #25.)
- The capture probe blocked a real command. Cursor's permission gates expect
  `{"permission": "allow"}` on stdout and treat a silent hook as a refusal -- witnessed
  live on Windows, where the probe's silence made Cursor reject the very command that was
  trying to read the capture report. "Always allows" meant "exits 0", and exit 0 is not an
  answer everywhere: the probe now replies allow in the agent's own dialect through the
  adapter's `respond()`, stays silent where silence is the documented protocol, and the
  witnessed behaviour is recorded in Cursor's matrix note (silence blocks, so the
  documented fail-open covers less than any-hook-problem).
- On Windows, a UTF-8 BOM on stdin turned every payload into mojibake under the console
  locale (cp1252), `json` failed at line 1 column 1, and the dispatcher allowed everything
  while the consumer believed it was gating. Witnessed live: a real Cursor session on
  Windows fired 115 hook events and the capture probe recorded every one of them only as a
  length. The fix is chock's, ported with its provenance: read bytes and decode
  `utf-8-sig` ourselves (`utf-16` as a fallback in the probe), never the platform locale.
- The capture probe threw away the evidence of why a payload did not parse -- a length
  cannot be diagnosed. Unparseable input now records shape-only facts: byte count,
  encoding that succeeded, BOM, first-character class, line counts. Still nothing of the
  content.
- The capture probe read the agent it was recording from an environment variable that
  `install` never set, so every payload was filed under `?` and the report could not hold
  them against any adapter. The agent name now rides as argv, wired at install time.
- The capture kit wired an unquoted interpreter path, which never launches when Python
  lives under a path with a space -- indistinguishable at capture time from a vendor whose
  hooks do not fire. Interpreter and probe path are now double-quoted, shell-agnostic
  between POSIX shells and cmd.exe (also chock's fix).
- An unmapped vendor event was answered four different ways across the adapters, and the
  most common was the worst: five relabelled it as the nearest canonical event, so a
  `TeammateIdle` payload reached a handler as `pre_tool` and invited a pre-tool policy to be
  evaluated against something that was not one. Two returned a non-canonical value and two
  raised, taking the hook down (and most agents fail open on a crashed hook). Every adapter
  now reports `contract.UNKNOWN`, which sits outside `EVENTS` so a handler matching the
  vocabulary cannot match it by accident, and the dispatcher allows without calling the
  handler at all.
- VS Code Copilot could parse `postToolUseFailure` and the matrix claimed `tool_failure`,
  but the hand-kept list in `claims()` had never included it — so real tool-failure payloads
  were claimed by no adapter, and an unidentified payload is allowed through. The claimable
  set is now derived from `EVENT_MAP` rather than kept by hand.
- The pre-commit hook did not watch `examples/vendor_payloads.py`, the file most likely to
  be edited for a docs change.
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
- `ARCHITECTURE.md`, hand-written: the layering boundary between primitives and policy,
  why `UNKNOWN` sits outside the event vocabulary, why detection must never guess between
  two adapters (with the four collisions found so far), how lossy translation is reported
  in all four primitives, and what each constraint costs. Deliberately not generated —
  the drift check that keeps `examples/generated` honest works because that output is
  deterministic, and prose is not.
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
- `.githooks/pre-commit` regenerates the vendor examples when a commit touches what they
  are generated from, so the pages land in the same commit as the change. Enable with
  `git config core.hooksPath .githooks`; CI remains the guarantee.
- `examples/generate.py --check` now prints a unified diff of what changed, so a red
  pipeline shows which behaviour moved without checking the branch out.
- Vendor example pages now cover **every hook each agent supports** (79 sections across 10
  agents), not one per agent: the payload, the normalized event, and what a decision
  produces there. Every page states what its claims rest on and tells adopters to verify
  against their own installation.
- `verified.basis` on every matrix row: a closed vocabulary (`live-run`, `vendor-source`,
  `vendor-docs`, `third-party-install`, `inherited`) saying what KIND of evidence a row
  rests on, queryable via `matrix.basis()`. Only Claude Code rests on a live run.
- `tools/capture.py`: record what an agent really sends and compare it against what the
  adapter claims, so a `vendor-docs` row can become a `live-run` one. The probe always
  allows, and payloads are reduced to shape before anything touches disk, so the capture
  file is safe to share. `tools/VERIFY.md` is the runbook.
- Junie CLI adapter: block, ask AND rewrite are all native on PreToolUse -- the only agent
  besides Claude Code needing no degradation at the gate.
- Tabnine CLI adapter: block on six of its eleven events, including AfterTool, which most
  agents treat as observation only.
- Replit's row moved from `inherited` to `vendor-docs`: its documentation was searched and
  no hook surface was found. Recorded as not-found rather than absent, since the search was
  of published docs and not of a running instance.
- Examples: cross-agent event log, cross-agent notifier.

[Unreleased]: https://github.com/open-coder-ai/agentseam/commits/main
