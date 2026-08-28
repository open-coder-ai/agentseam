# Changelog

All notable changes to this project are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Changed
- **No agent is rated `enforced` any more.** VS Code Copilot's `pre_tool` was the only row
  claiming `FAIL_CLOSED`, the strongest word in the vocabulary, and the vendor's own source
  contradicts it: `hookExecutor` treats exit 2 as a blocking error and *any other* non-zero
  exit as a `NonBlockingError`, which becomes a warning the tool call proceeds past. A
  guard that crashes, times out or is missing does not block. The row is `FAIL_OPEN`, its
  `ask` and `updatedInput` claims are unchanged (both are native and honoured in
  `languageModelToolsService`), and `post_tool`, `prompt_submit`, `stop` and
  `subagent_stop` gain the block they can really do. A test pins the absence so restoring
  `FAIL_CLOSED` anywhere has to come with the observation justifying it.
- VS Code Copilot's evidence record now cites the files it was actually read from
  (`hookTypes.ts`, `hookSchema.ts`, `hookCompatibility.ts`, `hookCommandTypes.ts`,
  `chatHookService.ts`, `hookResultProcessor.ts`, `languageModelToolsService.ts`) instead
  of two names, and is dated to that reading.
- Codex CLI's evidence record now says `live-run-partial` rather than `vendor-source`: two
  live sessions (Codex CLI 0.150.1, Windows, 74 payloads) claimed by this adapter, with
  `observed` naming the five canonical events actually seen fire and the row's other four
  still resting on source. The old record also cited
  `app-server-protocol/.../HookEventName.ts`, which is dropped and called out by name --
  that file is a ts-rs binding for the App Server's IDE-facing protocol, not the CLI hook
  dialect this adapter speaks, and citing it is precisely what put camelCase event names in
  this adapter for as long as it existed.

### Added
- **Every adapter now declares the decision words its vendor accepts**, and a test asserts
  `respond()` emits nothing outside that set. Each `DECISION_VOCABULARY` is cited to where
  the value is recorded — the vendor's source, its documentation, or the adapter's own
  docstring.

  This is the guardrail for a defect class found twice by hand in one week: `junie` emitted
  `"deny"` where the vocabulary is allow/ask/block, at all three of its permission gates.
  Most of these agents fail **open**, so an unrecognised decision is not a louder refusal —
  it is a *permitted action*, reported to the caller as a block. The rest of the suite could
  not see it, because it asserted the *shape* of a response and never asked whether the
  vendor had a word for it.

  Verified by reintroducing the Junie bug: the test fails with the exact word and event.

  **What it does not catch**, stated plainly: `claude_code`'s defect used a *valid* word in
  the *wrong envelope* (`permissionDecision` at events reading a top-level `decision`).
  Word-checking cannot see placement — reintroducing that bug leaves this test green. That
  class still needs a live contract experiment (`tools/probe_contract.py`).

  One vocabulary is marked `UNVERIFIED` — `tabnine`'s, which rests on nothing recorded
  anywhere in this repository. It is deliberately left as-is rather than guessed at, with a
  test pinning that it stays the only one, so the exception cannot quietly spread.

- **A second invariant: `respond()` may only speak a verdict where the matrix says one is
  read.** A decision word at a detect-only event is a refusal nobody reads — and worse than
  useless, because it is indistinguishable on the wire from a real gate verdict and invites
  a log or a downstream consumer to record a block that never happened.

  Writing it immediately found two more, both open "certain" items in the vendor-truth
  backlog and neither previously caught by any test: `devin` returned `{"decision":
  "block"}` at `post_tool`, `session_start` and `session_end`, and `gemini_cli` returned
  `{"decision": "deny"}` at `pre_compact`, `session_start` and `session_end` — each
  contradicting its own matrix row. Both now stay silent there; `devin` keeps recording the
  finding as `additionalContext` at the events that have that channel. Verified by
  reintroducing the `devin` case, which the test rejects by event and word.

### Fixed
- **`kimi_code` claimed a gate at four events that cannot block.** `UserPromptQueued`,
  `PermissionRequest`, `StopFailure` and `Interrupt` mapped onto `prompt_submit`, `pre_tool`
  and `stop` — canonical events the matrix rates blocking — while being fire-and-forget per
  the vendor and absent from `BLOCKING_EVENTS`. So `can_block("kimi_code", "prompt_submit")`
  answered True, a handler denied a prompt-injection attempt at a `UserPromptQueued`
  payload, and `respond()` dropped it in silence: a gate that reported a block and permitted
  the act.

  They now resolve to `UNKNOWN`, which keeps what is true and drops what is not. `claims()`
  still identifies these payloads — the consumer is not blinded to the moment — and `parse()`
  simply refuses to relabel a fire-and-forget event as a gate, so no policy keyed to a
  canonical event fires on one.

  This removes the last exception from the silent-gate invariant. It shipped with these four
  pinned; rather than excusing them, the mislabelling is gone, so there is nothing left to
  excuse and no exception list survives.

- **The capture probe was unrunnable under PowerShell, on every agent.** `capture.py` wired
  `"C:\py.exe" "probe.py" agent` — correct for POSIX shells and `cmd.exe`, and chosen for
  interpreters under paths with spaces. PowerShell is the gap: a line *beginning* with a
  quoted path parses as a string expression, not an invocation, so nothing runs. Two vendors
  are now known to wrap hooks that way on Windows (Codex; VS Code Copilot via
  `hookExecutor.ts`'s `getShellCommand`), and both have per-platform override fields they now
  use — but the other ten record no such field, leaving the command string as the only lever.

  It is now unquoted whenever the interpreter path has no spaces, which parses in command
  mode in all three shells and needs no vendor support. A path *with* spaces keeps its
  quotes — there is no single string that works everywhere — and `install` warns when that
  combination meets an adapter with no override, rather than silently picking one shell.
  Safe here in a way it would not be in a real guard: the probe always allows, so an
  invocation that fails to resolve costs a capture, not a gate.

### Added
- `capture.py install --agent detected` wires every agent whose config location exists, so a
  capture evening records whichever agent actually gets opened instead of one guess. Wiring
  several at once also makes double-firing visible — that is how Cursor was found to load
  Claude Code's config as well as its own, with every event arriving twice.

- **A regression introduced and caught in the same change: `devin`'s `PermissionRequest`
  stopped blocking.** Scoping `respond()` to a blocking-events tuple (above) left out
  `PermissionRequest`, which maps to canonical `pre_tool` — so a deny at a permission gate
  began returning `""`, which is an allow. Found by re-reading the diff against `main`
  rather than by any test, which is not a net worth relying on.

  Hence a third invariant: **a deny at a blocking event is never silent.** It drives *every*
  vendor event name rather than the shipping payload corpus, because the corpus only
  exercises each canonical event's primary vendor name and the aliases are exactly where
  this hides. Verified by reintroducing the regression.

  It tests "said something", not "used a decision word" — `cursor` refuses at
  `beforeSubmitPrompt` with `{"continue": false}` and no decision word at all, which is a
  real block in that dialect; a word-based test would have called it a bug.

  Four `kimi_code` events are pinned as known exceptions (`UserPromptQueued`,
  `PermissionRequest`, `StopFailure`, `Interrupt` — the open `kimi_code.py:~50`), with a
  second test asserting they are *still* silent so the exception expires if it stops being
  true. Pinned rather than fixed: the remedy is a design choice between unmapping them and
  correcting the matrix claim, and that is not mine to make silently.

- **VS Code Copilot's hooks never ran on Windows** — the identical defect fixed for Codex in
  #52, found in the vendor's source before it cost a capture session. `hookExecutor.ts`'s
  `getShellCommand` spawns `powershell.exe -ExecutionPolicy Bypass -NoProfile -NoLogo
  -Command <hookCommand>` whenever `ComSpec` is `cmd.exe` — the Windows default — and
  PowerShell will not RUN a line beginning with a quoted path: it parses as a string
  expression, so nothing executes. Every command agentseam installs begins with a quoted
  interpreter path. Installs now also emit the vendor's own `windows` platform override
  (`normalizeHookCommand` in `hookSchema.ts`) carrying PowerShell's `&` call operator, while
  `command` keeps the POSIX form so the exact interpreter path that installed the hook
  survives. The shared rule now lives in one place (`adapters/_windows.py`) rather than in
  two copies that could drift.

- **Every `prompt_submit` and `stop` deny on Claude Code was silently discarded.**
  `respond()` emitted `hookSpecificOutput.permissionDecision` at every event. A live
  response-contract experiment against Claude Code 2.1.247 (Windows, 2026-08-28) settled
  what each event actually reads:

  | event | `{"decision": "block"}` | `hookSpecificOutput` | exit 2 |
  |---|---|---|---|
  | `UserPromptSubmit` | honoured | **ignored** | honoured |
  | `Stop` | honoured | **ignored** | honoured |
  | `PreToolUse` | — | **honoured** | — |

  So the handler refused, the dispatcher reported a block, and the prompt reached the model
  anyway — on the most-used adapter in the matrix. The verdicts come from the agent's own
  behaviour, not the hook's claim: at `UserPromptSubmit` the trial prompt asked the agent to
  write a marker file and under `hookSpecificOutput` the file appeared; at `Stop` the agent
  carried on and the hook re-fired with `stop_hook_active` set.

  `prompt_submit` and `stop` now emit the top-level `{"decision": "block", "reason": ...}`,
  with `ask` and `rewrite` degrading to a block that names the degradation. `exit 2` works
  at both and is deliberately not used — it collapses to 1 under the PowerShell wrapper some
  vendors apply (which is what made the exit-code path useless on Codex/Windows) and it
  leaks the hook's full command line into the UI. `pre_tool` keeps `permissionDecision`, and that
  was checked in the same round rather than assumed — a deny there blocked the `Write`
  outright, and the agent's next `Bash` call too. So all three blocking events this row
  claims now rest on an observation rather than on inference from the other two. The
  observation-only events get silence instead of a verdict nothing read.

  Documentation could not settle this. Two reads of the vendor's own hooks page disagreed,
  and one of them said these events had no JSON decision control at all — which is why the
  fix waited for a live run rather than a third reading.

- **Junie's gate emitted a decision word the vendor does not accept.** `respond()` returned
  `{"decision": "deny"}` at `PreToolUse`, `UserPromptSubmit` and `PermissionRequest`. Both
  places this repository records Junie's gate vocabulary — the adapter's own module
  docstring and its matrix note — give it as **allow / ask / block**, and `respond()`'s own
  `Stop` branch already spelled it `block`; only the permission branch said `deny`, a value
  nothing here records Junie as understanding. Junie **fails open** (non-zero exits other
  than 2 are warnings and execution proceeds), so an unrecognised decision value at the
  strongest gate in the matrix is not a louder refusal — it is no refusal at all, and every
  deny and every degraded rewrite went through. `ask` was already correct and is unchanged.
  The tests that pinned `deny` were pinning the bug, including one named
  `test_block_and_ask_are_native`.

- **The capture probe answered in the wrong agent's dialect, and that blocks work.** The
  probe chose its response dialect from `sys.argv[1]` — the label it was *installed* under
  — rather than from the payload in front of it. Cursor loads Claude Code-format hooks as
  well as its own (confirmed live 2026-08-27: with both `.cursor/hooks.json` and
  `.claude/settings.json` present, every event fired **twice**, once per config), so a
  probe installed as `claude_code` really does receive Cursor's own `preToolUse` payload —
  and answered it with `hookSpecificOutput`, which Cursor does not read. That is
  indistinguishable from silence, and this probe's own source already records that silence
  at a Cursor permission gate is treated as a **refusal** and blocks the user's real
  command (witnessed live on Windows, where it blocked the very command reading the capture
  report). The responding adapter is now chosen by `adapters.detect(payload)`; `argv` still
  attributes the *record*, which is how the double-fire was spotted in the first place. Two
  guards on the fallback: when `detect()` declines on a genuine tie (tabnine/gemini_cli
  share an envelope by design) the argv label is used only if that adapter actually
  `claims()` the payload, and an event resolving to `UNKNOWN` is never answered at all —
  there is no recorded output contract for an event we cannot name.

- **Cursor's read gate dropped the file text it was handed.** `beforeReadFile` (and
  `beforeTabFileRead`) put the file's contents at the top level of the payload, with no
  `tool_input` and no `edits` — the shape `tests/payloads.py`'s own committed `CU_READ`
  fixture carries. `_content_of` read only those two nested locations, so `event.content`
  was `None` on the one gate that can still stop a secret being read into the model's
  context: a handler written as `"TOKEN" in (event.content or "")` — the pattern
  `dispatch.py`'s own docstring advertises — saw nothing and allowed. `path` already read
  the same payload's top-level `file_path`; only content was missed.
- **Cursor's prompt gate was installed fail-open.** `hook_config()` set `failClosed` by
  asking `name in _PERMISSION_GATES`, but that set answers a different question — which
  gates speak the `{"permission": ...}` dialect. `beforeSubmitPrompt` is a real gate that
  speaks `continue` instead (`respond()` has a branch returning `{"continue": false}` on a
  deny), so it fell through the gap. Cursor fails **open** by default, so a prompt guard
  that crashed or was missing silently permitted the prompt it was installed to stop — on
  the one agent whose matrix row rates `prompt_submit` `fail-configurable`, i.e. our choice
  to make. The two meanings are now separate sets.

- **VS Code Copilot's hooks file was never parseable, and its events were the wrong
  vendor's** -- four defects found by reading microsoft/vscode from a clone rather than
  from the docs, each of which failed silently.
  (1) *`agentseam install vscode_copilot` wired nothing at all.* `hook_config()` emitted
  `{"version": 1, "hooks": [{"event": ..., "command": ...}]}`. VS Code's
  `parseCopilotHooks` iterates `Object.keys(root.hooks)` and resolves each key to a hook
  type; over a **list** those keys are `"0"`, `"1"`, `"2"`, which resolve to nothing and
  are skipped. The file parses, nothing is reported, and zero hooks are installed. The
  shape is now `{"hooks": {"PreToolUse": [{"type": "command", "command": ...}]}}`, and the
  top-level `version` is gone -- `hookFileSchema` keys its `if/then` on that field and its
  presence selects the Copilot CLI branch, which requires `bash`/`powershell` and rejects
  `command`.
  (2) *Event names were the other product's.* `HOOKS_BY_TARGET` in `hookTypes.ts` carries
  two maps: VS Code agent mode uses PascalCase (`PreToolUse`, `UserPromptSubmit`, `Stop`
  ...), identical to Claude Code's, and the GitHub Copilot CLI uses camelCase
  (`preToolUse`, `userPromptSubmitted`, `agentStop` ...). This adapter used camelCase
  everywhere, so it wrote CLI names into VS Code's own file and **claimed only camelCase
  payloads -- meaning it never claimed a real VS Code payload**. Those went to
  `claude_code` alone and were answered in Claude Code's dialect, which happens to match at
  PreToolUse and matches nowhere else. Both spellings now parse; `timestamp`, which
  `chatHookService.executeHook` merges into every VS Code payload, is what separates them.
  `SessionStart` stays deliberately ambiguous: Tabnine sends `timestamp` too and shares
  that one event name, and both agents are `detect` there, so declining costs no gate.
  (3) *`tool_failure` was an event no vendor has.* `postToolUseFailure` is in neither map
  and is not a `HookType`; the config key resolved to nothing and was dropped. It is
  removed from the adapter and from the matrix row, which had been advertising it.
  `Stop`, `SubagentStart` and `SubagentStop` -- real events that were missing -- are added.
  (4) *One gate shape at every event.* `respond()` emitted the PreToolUse
  permission-decision JSON everywhere. Elsewhere that shape is not merely ignored:
  `UserPromptSubmit` and `PostToolUse` read a **top-level** `{decision: "block", reason}`,
  `Stop`/`SubagentStop` read the same two fields **nested** in `hookSpecificOutput` and
  discard the block if `reason` is empty, and `SessionStart`/`SubagentStart` run under
  `ignoreErrors: true` where even exit 2 is swallowed. A deny at prompt_submit was theater:
  the hook reported a block and the prompt reached the model anyway. `hookEventName` is now
  echoed from the payload rather than hardcoded to `PreToolUse`, because `_toHookResult`
  strips `hookSpecificOutput` outright when it does not match the event being run.
- VS Code Copilot's `post_tool` output is read from `tool_response`, the key
  `IPostToolUseHookCommandInput` actually declares. `tool_output` is Claude Code's key,
  assumed here, so `event.output` was `None` on every real PostToolUse payload and an
  output-inspecting policy was silently dead on this agent.

- **What Codex actually sends, from the first live capture of it (36 payloads, 2026-08-28)**
  -- two claims corrected against real traffic rather than inference.
  (1) *The write vocabulary was fiction.* `parse()` read `file_path`, `content`,
  `new_string`, `new_str` and `edits` -- Claude Code's write vocabulary, copied across on the
  assumption Codex shared it. The capture saw exactly two tool names, `Bash` and
  `apply_patch`, and **both carry only `tool_input.command`**. `apply_patch` is the
  file-writing tool and the patch text rides inside that command string, so `event.path` and
  `event.content` are `None` on every real Codex write: a handler written as
  `"SECRET" in (event.content or "")` never fires here, and a content policy has to gate on
  `event.command` instead. `new_string`/`new_str`/`edits` are removed (Codex has no MultiEdit
  and no payload ever carried them); `content`/`file_path`/`path` stay only as a generic
  fallback for MCP tools, which this capture did not exercise. The `CX_WRITE` fixture was an
  invented `Write` + `{file_path, content}` shape and is replaced with the captured
  `apply_patch` one.
  (2) *A real Codex `SessionStart` was claimed by claude_code.* Codex stamps `turn_id` on
  every mapped event except `SessionStart`, which is not turn-scoped --
  `SessionStartCommandInput` is `deny_unknown_fields` and defines exactly `session_id`,
  `transcript_path`, `cwd`, `hook_event_name`, `model`, `permission_mode`, `source`, every
  one of which Claude Code also sends. `claims()` required `turn_id`, so codex_cli rejected
  its own payload and claude_code claimed it alone: `detect()` answered confidently in the
  wrong dialect, which Codex rejects and therefore fails open. codex_cli now claims that
  shape too, making `detect()` decline as ambiguous -- the same posture tabnine and
  gemini_cli already take, and the honest one when two vendors are genuinely
  indistinguishable. A consumer resolves it by naming the agent.
- **Codex CLI hooks never ran on Windows, and their responses were rejected everywhere
  else** -- both found by finally getting a live capture out of a real Codex CLI 0.150.1
  install, and both fixed against the vendor's own source rather than inference.
  (1) *Nothing executed on Windows.* Codex runs hook commands through PowerShell there,
  where a command line beginning with a quoted path (`"C:\...\python.exe" "script.py"`) is
  parsed as a string expression, not an invocation -- a parse error, so the hook never ran.
  Every event failed with a bare "hook exited with code 1", and appending `> file 2>&1` to
  the command produced no file at all, which is what proved the line never reached
  execution. `install()` now also emits Codex's own `commandWindows` override
  (`HookHandlerConfig::Command` in `config/src/hook_config.rs`, preferred over `command` on
  Windows at `discovery.rs:512`) carrying the `&` call operator. That keeps `command` as the
  exact interpreter that installed the hook, rather than trading a verified path for a bare
  `python3` and hoping PATH resolves it.
  (2) *Responses were invalid at every event except a denied pre_tool.* `respond()` sent the
  PreToolUse `hookSpecificOutput.permissionDecision` shape everywhere, but each per-event
  output struct in `hooks/src/schema.rs` is `#[serde(deny_unknown_fields)]`: a key that event
  does not define does not get ignored, it makes Codex reject the entire response. Witnessed
  live as "hook returned invalid user prompt submit JSON output" on every single prompt.
  `respond()` is now event-aware, matching the matrix row and the vendor structs: `pre_tool`
  keeps the permissionDecision gate; `prompt_submit` and `stop` use the top-level
  `{"decision": "block", "reason": ...}` their structs actually define; the observation-only
  events define no verdict field and now stay silent. A bare allow is silence everywhere too
  -- `output_parser.rs` rejects `permissionDecision: "allow"` unless it carries
  `updatedInput`, and a rejected response is a hook error, which fails OPEN. The first real
  Codex payload this project has ever held is recorded as a fixture; it confirmed the
  PascalCase event names live and showed `permission_mode`/`transcript_path` are shared with
  Claude Code, leaving `turn_id` as the only observed discriminator.
- **Codex CLI's event names were the wrong casing everywhere: config file, outgoing
  response, and incoming-payload detection.** `codex_cli.py` believed Codex's hook events
  were camelCase ("preToolUse"), sourced from a `HookEventName.ts` binding that turns out to
  belong to the App Server's separate IDE-facing JSON-RPC protocol, not the plain CLI
  hook-subprocess dialect this adapter actually speaks. Verified against the real source
  (`openai/codex: config/src/hook_config.rs`, `hooks/src/schema.rs`,
  `hooks/src/engine/output_parser.rs`): Codex's hooks.json config keys, its runtime wire
  payload's `hook_event_name` value, and its expected response's `hookEventName` are all
  PascalCase, the same as Claude Code's. Three consequences, all fixed: (1) `hook_config()`
  wrote `{"preToolUse": [...]}` into `.codex/hooks.json` -- Codex's `HookEventsToml` only
  recognises its twelve PascalCase-named fields and silently drops anything else (no
  `deny_unknown_fields`), so the file parsed fine and Codex loaded *zero* hooks from it, no
  warning, no error, `agentseam install codex_cli` reporting success while wiring nothing.
  (2) `EVENT_MAP` never matched a real payload's `hook_event_name`, so `claims()` never
  recognised genuine Codex CLI traffic. (3) `respond()` echoed the wrong-cased value back in
  `hookSpecificOutput.hookEventName`. Fixing (2) surfaced a second, previously-masked bug:
  while matching stayed broken by the casing typo, `permission_mode` had quietly stopped being
  a safe discriminator between Codex and Claude Code (a live-captured Claude Code payload
  carries it too) without anything noticing, since codex_cli never claimed a real payload to
  test it against. `claims()` now keys on `turn_id` alone, the one field still unrefuted by a
  real payload. Also fixed while cross-referencing the real parser:
  `respond()`'s ASK branch emitted `permissionDecision: "ask"`, a value Codex's own
  `output_parser.rs` explicitly treats as an invalid hook response (`"PreToolUse hook returned
  unsupported permissionDecision:ask"`) -- and an invalid hook response fails OPEN, so asking
  silently allowed exactly what the handler wanted confirmed. ASK now degrades to DENY with an
  explanatory reason instead. `examples/generated/codex_cli.md` regenerated.
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
