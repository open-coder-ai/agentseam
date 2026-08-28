# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **`install()`'s ownership marker broke Codex CLI's hooks file outright**: `_mark()` tagged
  every dict with a `hooks` key, including the top-level container `hook_config()` returns,
  so `agentseam install codex_cli` wrote `{"_agentseam": "...", "hooks": {...}}`. Codex CLI
  (witnessed live here, 2026-08-27) refuses to parse the whole file over that one unexpected
  top-level key -- "unknown field `_agentseam`, expected `description` or `hooks`" -- so
  *every* hook silently never fires, not just ours; the install reports success and wires
  nothing. This is a known Codex bug independent of this project (openai/codex#30397, Codex
  < 0.143.0 rejecting an unexpected top-level `description` the same way, fixed by #30229) --
  chock's own Codex plugin emitter already works around it by never writing a top-level key
  besides `hooks`. `_mark()` now tags only a dict reached as a *list item* (where every
  adapter's owned entries actually live), never a container reached by plain dict traversal,
  so the top level is never touched for any agent. Regression tests assert the marker never
  appears at the top level for every JSON-config agent, and that codex_cli round-trips
  install/uninstall correctly.
- `tools/capture.py` could not run as a script at all: `main()` builds the `report`
  subcommand's parser with `cmd_report`, but the `from capture_report import ... cmd_report`
  line sat *after* the `if __name__ == "__main__": sys.exit(main())` guard, so running
  `python3 tools/capture.py <anything>` raised `NameError: name 'cmd_report' is not defined`
  before a single argument was parsed -- the exact tool `tools/VERIFY.md` walks a verifier
  through running first. Moved the import above the entry-point guard, keeping it after every
  other name in the module is bound (the reason it was pushed to the bottom in the first
  place) so `capture_report`'s own lazy `from capture import ...` still finds a fully
  initialized module.
- Antigravity's `respond()` Stop branch treated ASK and REWRITE identically to DENY, emitting
  `{"decision": "continue", "reason": "<handler's raw reason>"}` with no degradation note --
  unlike the gate branch just below it, which already annotates both. A handler asking for
  confirmation or a rewrite at Stop was unconditionally re-entered into the work loop with a
  reason that read as though it had asked to keep working; the user never learned
  confirmation was needed or that the change could not be expressed there. Now annotated the
  same way the gate branch already is.
- Antigravity's `stepIdx` -- the module docstring's own named pre/post correlation key -- was
  never plumbed into `event.tool_use_id`, which stayed `None` on the one agent that names a
  correlation field at all. A handler timing a gate decision against its post-tool result, or
  verifying a denied call produced no output, had nothing to key on.
- Tabnine's `respond()` decided whether to speak from `event.raw["hook_event_name"]` alone --
  `respond()` is public adapter API, and a consumer who replays a captured event or builds
  one directly (`raw` defaulting to `{}`, as other adapters permit) got silence at a real
  blocking event instead of the deny they returned. Now checks `event.event` against the
  four blocking events with a canonical mapping first, falling back to the raw vendor name
  for the two (`BeforeModel`/`AfterModel`) that have none.
- Junie's `PermissionRequest` -- the event whose inverted default (silence approves) is the
  adapter's headline hazard -- cannot be wired by `install()` on its own, since it shares
  canonical `pre_tool` with `PreToolUse` and `REVERSE_EVENT_MAP` names only one vendor event
  per canonical one. Nothing said this was deliberate rather than a coverage gap. Documented
  in the docstring and matrix note: bundling the two under one `pre_tool` install would hand
  a consumer an approve-by-default gate they did not ask for, so it must be wired by hand.
- **Claude Code's matrix row claimed `enforced` -- the strongest claim in the whole
  vocabulary -- at `pre_tool` and `prompt_submit` with no basis anywhere in this project**:
  not the docstring, not the note, not the evidence record, not the CHANGELOG. Every other
  agent's fail-mode claim is justified in its note; this was the one unsupported exception,
  and a consumer filtering for `enforcement_level == "enforced"` to pick a sole barrier
  would trust a guard that, if it crashed, may silently allow the very thing it was
  installed to stop. Downgraded to `FAIL_OPEN` (`best-effort`) pending a live observation
  that would justify closing it back up. `pre_compact`'s `block=True` had the same problem
  and is now `detect`-only. `examples/generated/claude_code.md` regenerated.
- VS Code Copilot's `FILE_WRITE_TOOLS` constant (`create_file`/`edit_file`/`apply_patch`) was
  declared and read by nothing, misleadingly implying write-tool-specific content extraction
  that does not exist -- `parse()`'s generic branch reads `content`/`newText`/`new_str`
  regardless of tool name. Removed the dead constant. The underlying gap it named -- neither
  `edit_file`'s nor `apply_patch`'s actual `tool_input` shape has been recorded from a real
  payload or the cited vendor source -- is left for a live capture rather than guessed at; a
  wrong key would silently read the wrong field.
- Devin's matrix row claimed `pre_compact` coverage by mapping `PostCompaction` onto
  canonical `PRE_COMPACT` -- but `PostCompaction` fires AFTER compaction, the adapter's own
  docstring already said so. A handler wired at `pre_compact` to flush or snapshot context
  before it is discarded -- the reason the event exists -- ran once the context was already
  gone, and `install('devin', ['pre_compact'])` silently wired the wrong moment. Left
  unmapped: `parse()` reports `PostCompaction` `UNKNOWN` rather than claim a "before" gate
  that is actually "after"; `install` now refuses `pre_compact` for devin with an actionable
  error instead of wiring it wrong. `examples/generated/devin.md` regenerated.
- Cursor's `postToolUseFailure` was missing from `_POST_HOC`, so a deny/ask at a failed
  tool call returned silence instead of the `{"additional_context": "observed after the
  fact..."}` detection record its sibling `postToolUse` gets for the identical fact (the
  call already happened). A policy flagging failed commands lost its only signal on Cursor.
  `examples/generated/cursor.md` regenerated.
- The matrix's `codex_cli` note still listed `model` among the fields that separate its
  payload from Claude Code's, while `codex_cli.claims()`'s own docstring says the opposite:
  `model` stopped counting as a discriminator because Cursor sends it too, and claiming on
  it made every real Cursor payload ambiguous. A maintainer trusting the (source-of-truth)
  note over the code could re-add `model` to `claims()` and reintroduce that exact
  regression. Reworded to match what the code actually does.
  `examples/generated/codex_cli.md` regenerated.
- Codex CLI's `respond()` dropped `decision.reason` on a REWRITE: the emitted JSON carried
  only `allow` + `updatedInput`, unlike `claude_code.respond` which already includes
  `permissionDecisionReason` when a rewrite has one. A handler explaining WHY a write was
  altered (e.g. "secret redacted; use env var") reached Codex with the changed content and
  no explanation. `examples/generated/codex_cli.md` regenerated.
- `tools/redact.py`'s `MAX_ENUM_LEN=48` destroyed real MCP tool names: `mcp__<server>__<tool>`
  routinely exceeds 48 characters, so a capture session gating MCP calls lost WHICH tool
  fired -- reduced to `<str:NN>` -- on exactly the surface several matrix rows most need
  verified. Tool-name-shaped keys (`tool_name`, `toolName`, `name`, `mcp_server_name`) now
  get a 128-char cap; other structural keys, and actual prose reusing one of these key
  names, are unaffected.
- Windsurf's two MCP events (`pre_mcp_tool_use`/`post_mcp_tool_use`) stored the constant
  vendor event name in `event.tool` instead of the MCP tool identity, so a cross-agent
  handler written as `event.tool in RISKY_TOOLS` (works on `claude_code`/`devin`) could
  never match a Windsurf MCP call -- `event.tool` was always the same string. `event.tool`
  now carries `<server>/<tool>` for these two events (per the real installation's own
  payload shape). Blocking and the vendor event name in log messages, which used to be
  read off `event.tool`, are now derived from `event.raw` instead so this does not regress.
  Separately, `install('windsurf', ['pre_tool'])` wired only `pre_run_command` --
  `pre_mcp_tool_use`, a documented BLOCKING gate mapped to the same canonical `PRE_TOOL`,
  was never wired by anything, so a `pre_tool` policy silently covered shell commands but
  not MCP tool calls. `hook_config` now wires both. `examples/generated/windsurf.md`
  regenerated.
- Claude Code's `InstructionsLoaded` and `FileChanged` carry no `tool_input` at all --
  `file_path` (and, for `InstructionsLoaded`, `content`) sit at the top level instead, per
  the project's own recorded example payloads. `parse()` only ever read from `tool_input`,
  so `event.path` (and `event.content`) were always `None` for both events -- a policy
  gating instruction-file loads or watched-file changes by path or content never fired.
  `examples/generated/claude_code.md` regenerated to reflect the fix.
- Kimi Code and Junie both claim Claude Code's wire protocol exactly (their own docstrings
  say so), but `parse()` in each read only `content`/`new_string` -- so MultiEdit's
  `edits[].new_string` and NotebookEdit's `new_source`/`notebook_path` were dropped, and a
  content policy that already works on claude_code's MultiEdit/NotebookEdit went blind on
  these two. Mirrors the fallback chain claude_code.parse already uses.
- `install` could **destroy a user's entire config**. `_load` returned `{}` on any parse
  failure, so the fragment was merged into an empty object and written back, discarding
  everything the file held. For Junie, whose `config.json` is the whole CLI configuration
  rather than a hooks-only file, a single stray byte -- a UTF-8 BOM from a Windows editor, a
  trailing comma, a half-saved edit -- cost the user their entire config. `_load` now
  tolerates a BOM (utf-8-sig, mirroring the runtime stdin fix) and raises `ConfigUnreadable`
  on anything still unparseable rather than returning `{}`, so `install` and `uninstall`
  stop and preserve the file instead of overwriting it. `installed()` stays a safe query and
  reports "not present" rather than raising -- including its TOML branch, which read the file
  with no guard and so crashed the query on a non-UTF-8 or unreadable config. This protected
  every JSON-config agent, not just Junie.
- Claude Code's `NotebookEdit` is listed in `WRITE_TOOLS`, so the adapter claims to gate it,
  but its cell body arrives as `new_source` -- a field `parse()` never read -- so
  `Event.content` was `None` and a content policy (secret scan, memory guard) saw nothing at
  a notebook write. Now read. MultiEdit and the other write tools were already handled; only
  NotebookEdit was dropped.
- A policy `reason` containing any character the platform console cannot encode crashed the
  response write before the exit code was emitted -- the output twin of the stdin BOM bug.
  On a Windows cp1252 console an emoji or a non-Latin word in a deny reason raised
  UnicodeEncodeError inside `run()`; for Windsurf, whose only block signal is the exit code,
  the process then exited 1 instead of 2 and the action proceeded, and for every
  JSON-dialect agent the deny body never reached stdout. Both fail OPEN. `run()` now writes
  UTF-8 bytes through the stdout buffer, so no policy reason can crash the gate.
- VS Code Copilot parsed `userPromptSubmitted` to `prompt_submit` but never read the prompt
  text, so `event.prompt` was `None` and any prompt-based policy on this agent was silently
  dead. Its envelope-twins claude_code and gemini_cli both read `prompt`; now it does too.
- **13 of the 15 shipping payloads that render the published vendor pages resolved to the
  wrong adapter, and Tabnine's gates were dead.** Gemini CLI claimed on
  `client_type in (None, ...)` -- the absence of somebody else's nameplate -- and its own
  payload is a strict subset of the four vendors that share its event names, so it swallowed
  every unlabelled payload. A `deny` at Tabnine's `pre_tool`, `prompt_submit` or `stop`
  produced *silence* under auto-detection. Gemini now defers to any adapter holding positive
  proof (Tabnine's `timestamp`, Junie's `project_path`, Devin's `prompt_id`, Codex's
  `turn_id`, Claude Code's observed markers), and Claude Code defers to `timestamp` for the
  same reason it already deferred to the other two. The shipping Claude Code payloads now
  carry `transcript_path` and `permission_mode`, which every live payload had -- without
  them the corpus could not exercise the discrimination the adapter relies on, which is how
  a docs-era corpus agreed with a broken rule all the way to production.
- The collision test walked `tests/payloads.py` and never `examples/scenarios.py`, so the
  corpus that generates the published docs was unchecked. It is checked now, with the two
  genuinely irreducible cases pinned and a second test that fails if a pinned exception
  stops being true.
- `agentseam install all` crashed with a traceback and wired nothing -- including both
  commands the example docstrings document. At least one of twelve agents lacks a hook for
  any given event set, and `install()` raising for an unwireable event is deliberate; `all`
  propagating that raise let one agent's gap take down the eleven that could be wired. It
  now mirrors the permissions primitive: wires what can be wired, names each skipped agent
  with the events it lacks on stderr, and exits non-zero so a script still notices.
- **Claude Code detection was broken against current builds, and the payloads went to the
  wrong adapter.** `claims()` treated `prompt_id` as proof a payload was Devin's rather than
  Claude Code's; Claude Code now sends it on nearly every event. A live capture claimed 4 of
  42 real payloads -- and the other 38 were claimed by Devin, alone, so `detect()` returned
  "devin" with no ambiguity to stop it. A `deny` then rendered as `{"decision": "block"}`,
  which Claude Code does not read: the gate was silently open on the one agent whose row
  says `live-run`. Both adapters now discriminate on fields *observed* from Claude Code
  instead of on a field it was assumed to lack, and the fixture corpus gained payloads
  shaped like the ones a real session produces.

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
