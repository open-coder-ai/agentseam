# Dialect families: engines as code, vendors as data

Design document (W31, design only — no implementation). All file:line citations are at
main `99ef35d`. The goal, in the owner's words: *"Tomorrow a new vendor comes in, we
should be dropping json data or config file and the core engine should be able to emit
based on json or config data we provided, rather than re-writing code for every vendor
if possible."*

Everything below marked **[v]** was verified by recount at the pin; **[h]** is a
hypothesis to verify during implementation.

## 1. What actually varies — recounted, not trusted

Method **[v]**: parse each adapter module, extract the four functions, strip docstrings,
re-parse the unparsed source, hash `ast.dump(..., include_attributes=False)`. Baseline
suite at the pin: 1206 passed, 4 skipped.

| function | distinct / 12 | identical groups |
| :--- | :--- | :--- |
| `claims` | 11 | junie = tabnine (bodies identical; only the `MARKER` constant differs, `junie.py:40` vs `tabnine.py:49`) |
| `parse` | 12 | none |
| `respond` | 12 | none |
| `hook_config` | 9 | claude_code = gemini_cli = grok = junie (`claude_code.py:177-188`, `gemini_cli.py:124-134`, `grok.py:118-128`, `junie.py:105-116`) |

Correction to the dispatch brief **[v]**: not every adapter defines `EVENT_MAP` —
antigravity has none at module level; its vendor payloads carry no event name, so the
mapping is inlined where the inferred name is resolved (`antigravity.py:57`). The other
11 define all of `AGENT`, `EVENT_MAP`, `REVERSE_EVENT_MAP`, `DECISION_VOCABULARY`,
`CONFIG_PATH`.

"12/12 distinct" overstates how much is *dialect*. The distinct hashes mix three kinds
of variance:

1. **Grammar** — the shape a vendor reads/writes (`hookSpecificOutput` vs a top-level
   `decision` word vs `permission` vs an exit code). Small closed set; this is code.
2. **Vocabulary** — which words fill the grammar, which key spellings fill the payload
   (`tool_input` vs `toolInput`, `file_path` vs `absolute_path` vs `TargetFile`),
   which markers identify the vendor. Pure data; this is config.
3. **Shape inference** — vendors whose payloads carry no event name and must be
   classified structurally (antigravity, cursor, windsurf). Per-vendor code, small.

## 2. Taxonomy

### 2.1 The two axes

**Payload envelope (parse side):**

| envelope | adapters | evidence |
| :--- | :--- | :--- |
| snake_case `hook_event_name` + `tool_input` (dict or JSON string) | claude_code, codex_cli, devin, junie, kimi_code, tabnine, gemini_cli | `claude_code.py:83-86`, `codex_cli.py:55-64`, `devin.py:59-68`, `junie.py:51-63`, `kimi_code.py:71-86`, `tabnine.py:58-69`, `gemini_cli.py:67-79` |
| same structure, camelCase keys (`hookEventName`, `toolInput`, `toolName`, `sessionId`) | grok | `grok.py:60-86` |
| dual-cased (both spellings accepted) + memory-tool argument scheme | vscode_copilot | `vscode_copilot.py:27-42,61-62,77-86` |
| top-level `command`/`edits`/`conversation_id`; event name sometimes absent, inferred from shape | cursor | `cursor.py:96-98,112-119` |
| `tool_info` sub-object + `trajectory_id`; event inferred when unnamed | windsurf | `windsurf.py:19-32,38-56` |
| no event name ever; `toolCall.args` with PascalCase keys (`CommandLine`, `TargetFile`, `CodeContent`, `ReplacementChunks`) | antigravity | `antigravity.py:13-15,25-31,45-67` |

**Verdict grammar (respond side)** — the safety-critical axis; a wrong response fails
open:

| grammar | shape | spoken by (event groups) |
| :--- | :--- | :--- |
| G1 flat decision | `{"decision": W, "reason": R}` ± extras | gemini_cli all gates (`gemini_cli.py:97-121`); junie all gates (`junie.py:76-102`); tabnine (`tabnine.py:87-104`); grok deny-only (`grok.py:92-110`); antigravity pre-tool, plus `continue`/`stop` words at Stop (`antigravity.py:73-107`); devin verdicts (`devin.py:104-113`); claude_code, vscode_copilot, codex_cli at prompt_submit/stop only (`claude_code.py:141-145`, `vscode_copilot.py:138-141`, `codex_cli.py:91-94`) |
| G2 permission gate | `{"hookSpecificOutput": {"hookEventName", "permissionDecision", "permissionDecisionReason", "updatedInput"?}}` | claude_code pre_tool (`claude_code.py:158-174`); vscode_copilot pre_tool (`vscode_copilot.py:155-171`); codex_cli pre_tool (`codex_cli.py:107-127`); kimi_code at all three of its gates, deny-only (`kimi_code.py:103-126`) |
| G3 hookSpecificOutput extras | `additionalContext` / nested `decision: block` / `tool_input` rewrite | claude_code (`claude_code.py:128-134,144`); vscode_copilot nested block (`vscode_copilot.py:143-147`); devin context + `updatedInput` (`devin.py:91-99,115-117`); gemini_cli rewrite (`gemini_cli.py:119-120`) |
| G4 permission object | `{"permission": W, "user_message", "agent_message", "updated_input"?}` + `{"continue": bool}` + `{"additional_context"}` | cursor only (`cursor.py:150-200`) |
| G5 exit code | reason text + exit 2; no JSON | windsurf only (`windsurf.py:62-88`) |

### 2.2 The families

Assignment is by *grammar set drawn from* plus payload lineage — the two things a
shared engine must implement. A family of one is an honest answer.

| family | members | why here |
| :--- | :--- | :--- |
| **F1 `hook_json`** (5) | claude_code, vscode_copilot, codex_cli, kimi_code, devin | All five: PascalCase Claude-Code event names (`claude_code.py:30-43`, `codex_cli.py:26-36`, `kimi_code.py:31-48`, `devin.py:26-34`, `vscode_copilot.py:27-42`), snake_case envelope, mutual-disambiguation markers (`turn_id` `codex_cli.py:50`, `prompt_id` `devin.py:56`, `client_type` `kimi_code.py:68`, `looks_like_claude_code` `claude_code.py:63-65`), and every member emits a `hookSpecificOutput` body somewhere (G2/G3). kimi_code is explicitly Claude Code's shape (`allow_semantics.py:66-69`). |
| **F2 `flat_decision`** (4) | gemini_cli, tabnine, junie, grok | Verdicts are only ever a top-level decision word (G1). gemini_cli and tabnine share the `BeforeTool`/`AfterTool`/`BeforeAgent`/`AfterAgent`/`PreCompress` event vocabulary (`gemini_cli.py:24-32`, `tabnine.py:26-34`); junie and grok use CC event names but never a CC response shape. grok's camelCase payload keys are a key-spelling table, not a grammar. |
| **F3 `cursor`** (1) | cursor | Own grammar G4; per-gate ask-honouring table (`cursor.py:51-57`); shape-inferred claims/parse (`cursor.py:96-98,112-119`); `failClosed` hook wiring (`cursor.py:225-226`). Nothing to merge with. |
| **F4 `windsurf`** (1) | windsurf | Only exit-code-verdict vendor (G5); `tool_info` envelope; empty decision vocabulary (`windsurf.py:59`). |
| **F5 `antigravity`** (1) | antigravity | Event-less payloads classified by shape (`antigravity.py:25-31`); PascalCase argument scheme; G1 words at the gate but a distinct `continue`/`stop` word table at Stop; documented 7-word vocabulary (`antigravity.py:70`) mostly unexercised by `respond`. Its verdict *renderer* is F2's G1 — the engine can share that function — but its parse shares nothing. |

Judgment calls, stated: **devin** straddles — G1 verdict words (`approve`/`block`,
`devin.py:81`) but F1 payload lineage and G3 extras; filed under F1 because a bundle
for devin needs the `hookSpecificOutput` renderer and the CC claims discipline, which
F2 members never need. **junie** is the mirror case (CC payload, pure-G1 responses)
and is filed under F2 because its bundle needs only G1. If implementation finds these
placements awkward, moving one vendor between F1/F2 is a config edit under this design,
not a rewrite — that robustness is the point of the grammar × vendor table.

## 3. The vendor config schema

### 3.1 The line, drawn first

**Config may carry**: strings, booleans, ordered lists of strings, and flat maps of
those. Nothing else. No conditionals, no expressions, no templates beyond named `{}`
slots filled by the engine, no embedded code. A config format expressive enough to
encode arbitrary behaviour is a worse programming language with no tests and no
debugger; this design refuses it. The test of the line: if a vendor difference can be
expressed as *which word / which key / which flag / which list order*, it is config;
if it needs *branching on payload content* beyond ordered-key fallback and membership
tests the engine already performs, it is dialect code in the family module.

Consequences, applied to today's code:

| stays code (engine / family module) | becomes config |
| :--- | :--- |
| The five grammar renderers G1–G5 | which grammar each event group uses, and the word tables filling it |
| Ordered-fallback field extraction machinery, `tool_input_of` (`contract.py:139-150`) | the per-vendor key chains (e.g. path = `file_path→absolute_path→path` `gemini_cli.py:79`; content gated to write tools `gemini_cli.py:71-73`; output = `last_assistant_message` `junie.py:65`) |
| `degrade()` semantics (`dispatch.py:26-38`) and its generated-runtime twin (`bundler_templates.py:26-40`) | per-gate capability flags (`honours_escalate`, `honours_transform`, `honours_block`) and the degradation-note strings, verbatim from today's adapters so wire output stays byte-identical |
| Shape-inference `claims`/event-naming for cursor, windsurf, antigravity (`cursor.py:96-98`, `windsurf.py:27-32`, `antigravity.py:25-31`) | marker-based `claims`: required markers, foreign markers, client_type allowlists (`junie.py:45-48`, `tabnine.py:52-55`, `gemini_cli.py:57-64`, `codex_cli.py:43-52`) |
| vscode_copilot's memory-tool argument scheme (`vscode_copilot.py:77-83,103-107`) | `MEMORY_TOOLS` / `WRITE_TOOLS` / `SHELL_TOOLS` name lists |
| kimi's TOML emitter (`kimi_code.py:155-164`) — one renderer, selected by `config_format` | `config_path`, `config_format`, hook-entry wrapper style and extra entry fields (`commandWindows` `codex_cli.py:137`, `name` `tabnine.py:113`, `failClosed`+`version` `cursor.py:225-228`, group nesting `antigravity.py:117-127`, no-wrapper `devin.py:121-132`, extra `pre_mcp_tool_use` wiring `windsurf.py:106-107`) |

### 3.2 One entry, worked (gemini_cli)

```jsonc
{
  "agent": "gemini_cli",
  "display": "Gemini CLI",                    // fills degradation-note templates
  "family": "flat_decision",
  "config_path": ".gemini/settings.json",     // gemini_cli.py:137
  "config_format": "json",
  "needs_trust": false,                       // grok: true (grok.py:131)
  "events": {                                 // gemini_cli.py:24-32
    "BeforeTool": "pre_tool", "AfterTool": "post_tool", "BeforeAgent": "prompt_submit",
    "AfterAgent": "stop", "SessionStart": "session_start", "SessionEnd": "session_end",
    "PreCompress": "pre_compact"
  },
  "wire_events": {},                          // only where not the exact inverse:
                                              // grok.py:44-55, kimi_code.py:49-60 collapse
                                              // many-to-one and pin the emit direction
  "claims": {                                 // gemini_cli.py:57-64
    "event_key": "hook_event_name",
    "client_types": [null, "gemini_cli", "gemini"],
    "reject_markers": ["timestamp", "project_path", "prompt_id", "turn_id"],
    "reject_probes": ["looks_like_claude_code"]   // named engine predicate, not code-in-config
  },
  "fields": {                                 // ordered fallback chains, gemini_cli.py:67-86
    "tool": ["tool_name"],
    "command": ["tool_input.command"],
    "path": ["tool_input.file_path", "tool_input.absolute_path", "tool_input.path"],
    "content": ["tool_input.content", "tool_input.new_string", "tool_input.new_str"],
    "content_only_for_write_tools": true,
    "output": ["tool_output", "tool_response"],
    "prompt": ["prompt", "user_message"],
    "session_id": ["session_id"],
    "cwd": ["cwd"]
  },
  "tools": { "write": ["write_file", "replace"], "shell": ["run_shell_command"] },
  "verdicts": {
    "vocabulary": ["allow", "deny", "ask"],   // gemini_cli.py:89
    "vocabulary_basis": "verified",           // tabnine: "unverified" (tabnine.py:83-84)
    "bare_allow": "inert",                    // allow_semantics.py:70-77 key, cross-checked
    "answer_events": ["BeforeTool", "AfterTool", "BeforeAgent", "AfterAgent"],
    "gates": {                                // gemini_cli.py:104-121
      "BeforeTool": { "grammar": "G1", "honours_escalate": true,  "honours_transform": true },
      "AfterTool":  { "grammar": "G1", "honours_escalate": false },
      "BeforeAgent":{ "grammar": "G1", "honours_escalate": false },
      "AfterAgent": { "grammar": "G1", "honours_escalate": false }
    },
    "words": { "allow": "allow", "deny": "deny", "ask": "ask", "block": "deny" },
    "transform_grammar": "hook_specific_tool_input",   // gemini_cli.py:119-120
    "degrade_notes": {                        // verbatim today's strings, gemini_cli.py:109-117
      "ask_unhonoured": "%s (confirmation required; %s cannot prompt from a hook)"
    }
  },
  "hook_entry": { "wrapper": "hooks_map", "entry_extra": {}, "matcher": true }
}
```

Field names above (`honours_escalate`, `honours_transform`, `transform_grammar`) follow the
post-W35 ACS vocabulary (`contract.py`: `escalate`/`transform`), not the pre-ACS `ask`/
`rewrite` this section was drafted with at W31, before ACS alignment was sequenced ahead of
D2 (org-plan `plan/agentseam-project.md`: "D2 schema (written in ACS words)"). Vendor
wire-word *data* is untouched by that rename: `vocabulary`/`words` above are correct as
written, because that is the literal word gemini_cli's own dialect speaks on the wire, not
agentseam's name for the concept.

Where the degradation lives (the brief's codex question): `honours_escalate: false` on the
gate + the vendor's note string. codex_cli's ask→deny with *"Codex CLI does not support
ask; asking would fail open"* (`codex_cli.py:121-124`) is a flag plus a string — no
conditional survives in config. The engine's degrade step already exists twice
(`dispatch.py:26-38`, `bundler_templates.py:26-40`); it gains word/flag lookups and
loses nothing.

### 3.3 What config deliberately does NOT absorb

- **The capability matrix.** Matrix rows stay their own data with `version`/`date`/
  `method` evidence (`matrix_data.py:29-229`, `matrix_evidence.py:7-200`). Vendor
  config *references* its matrix row; a consistency test asserts config gates ⊆ matrix
  block-capable events and `config_path` agreement. Folding the matrix into vendor
  config would let a config edit silently widen a capability claim past its evidence —
  the discipline AGENTS.md guards ("claims never exceed capability_matrix").
- **`allow_semantics`.** The bare-allow audit (`allow_semantics.py:34-122`) keeps its
  prose evidence; config carries only the enum (`bare_allow`), cross-checked by test.
- **Shape inference.** cursor/windsurf/antigravity event classification stays code.
  Encoding "if `terminationReason` in payload then Stop" (`antigravity.py:27-31`) as
  config rules is the worse-programming-language trap; three small functions are
  cheaper than a rule interpreter.

Storage: one JSON file per vendor, `src/agentseam/data/vendors/<agent>.json`, loaded
by the PR #89 loader pattern (`_data.py` on branch `chore/data-tables-out-of-python`,
https://github.com/open-coder-ai/agentseam/pull/89 — open at dispatch; if it lands
first, reuse its loader; if not, this work ships its own copy of the same 28-line
loader). A `schema.json` beside them; validation is a test, not a runtime cost.

## 4. The bundle story

Today `bundle()` splices contract + the adapter + adapter-dir cross-imports +
`_windows.py` + a runtime (`bundler.py:133-187`), promising "same agentseam version →
identical bytes" (`bundler_templates.py:15-17`). Measured at the pin **[v]**:

| bundle | lines | | bundle | lines |
| :--- | ---: | :--- | :--- | ---: |
| claude_code | 439 | | devin | 407 |
| cursor | 480 | | kimi_code | 414 |
| vscode_copilot | 459 | | gemini_cli | 410 |
| codex_cli | 408 | | antigravity | 398 |
| grok | 383 | | windsurf | 380 |
| junie | 374 | | tabnine | 373 |

Future composition — still one self-contained stdlib-only file, same promise, same
handler block:

```
# header (identical-bytes promise now covers engine + embedded config)   ~10
from __future__ import annotations; import json, sys                     ~5
# contract (unchanged)                                                   ~140
# family engine: hook_json | flat_decision | cursor | windsurf | antigravity
#   field-chain accessor + marker claims + parse        ~90
#   grammar renderers the family needs (G1..G3 worst case) + degrade notes ~110
#   hook-entry renderer                                  ~30
# VENDOR = { ...this vendor's config entry, inlined as a dict literal... } ~60-90
# runtime (main/degrade/_read_payload, unchanged shape, bundler_templates.py:21-116) ~95
```

Estimate **[h]**: F1 member ≈ 540–580 lines (vs 407–459 today, +20–30%); F2 member ≈
470–500 (vs 373–410); singletons roughly unchanged. Per-file growth is the price of
generality inside one file; the payoff is in the source tree: today's 12 hand-written
adapters are 1,811 lines (`wc -l src/agentseam/adapters/*.py` at the pin, minus
`__init__` and `_windows`) that become ~5 engine/family modules (~600–700 lines
total **[h]**) + 12 declarative entries. A 13th vendor in an existing family is one
JSON entry + a matrix row + fixtures — no code, which is the owner's goal verbatim.
Byte-stability is testable exactly as today (`test_bundler.py:35`), and a new
equivalence test must hold: generated-runtime wire behaviour == library wire behaviour
over every scenario × outcome.

## 5. What breaks

Owner decision 2026-09-01 (org-plan `plan/agentseam-project.md:21`): no adopters, the
public adapter API may change freely — but every existing test's *intent* survives or
is retired with a reason. The migration invariant that makes this cheap: **wire output
stays byte-identical during migration** (degradation strings carried into config
verbatim), so behaviour tests prove the refactor rather than fighting it.

Keep `adapters.get(agent)` returning a module-like object (family engine bound to a
config entry) exposing today's surface: `AGENT`, `EVENT_MAP`, `REVERSE_EVENT_MAP`,
`DECISION_VOCABULARY`, `CONFIG_PATH`, `claims/parse/respond/hook_config`, plus the
lookup attributes (`WRITE_TOOLS`, `SHELL_TOOLS`, `CLIENT_TYPE`, `MARKER`,
`NEEDS_TRUST`, `CONFIG_FORMAT`, `MEMORY_TOOLS`, kimi's `render_config`). Then:

**Survive unchanged** (all drive the public surface with real payloads):
`test_dispatch.py`, `test_parse_is_total.py`, `test_unknown_events.py`,
`test_allow_is_vendor_default.py`, `test_fail_closed_gates_are_answered.py`,
`test_vendor_lookups.py`, `test_matrix.py`, `test_decision_vocabulary.py` (all but one,
below), the 12 per-adapter wire suites (`tests/test_adapter_*.py`, ~1,400 lines — they
become the family engines' conformance load; none die), packaging/install/cli/
instructions/capture suites (untouched paths).

**Die, intent re-homed:**

| test | why it dies | intent, re-homed |
| :--- | :--- | :--- |
| `test_the_unverified_vocabulary_is_still_only_tabnine` (`test_decision_vocabulary.py:89-94`) | greps per-vendor `.py` files that will no longer exist | `vocabulary_basis == "unverified"` exactly for tabnine, asserted against config — a derivation, not a string-presence check |
| `test_cross_adapter_dependency_is_inlined_where_actually_used`, `test_windows_helper_is_inlined_only_where_the_adapter_actually_needs_it` (`test_bundler.py:83-97`) | no adapter-dir cross-imports remain to splice | engine+config splice correctness: exactly one family engine and exactly one `VENDOR` literal per bundle |
| `test_bundle_is_byte_stable`, compile/no-import/handler-slot bundle tests (`test_bundler.py:35-80`), `check_stdlib_only.py`, `test_bundler_subprocess.py` | not dead — re-targeted at the new composition, assertions unchanged | same |

**Must be written:**

1. Config schema validation: every `data/vendors/*.json` validates; unknown keys are
   an error (a typo'd `honours_escalate` must fail loud, not fail open).
2. Config completeness: every `ADAPTERS` name is config-backed; every config gate maps
   to a matrix block-capable event; `config_path`/`bare_allow` agree with
   `MATRIX`/`ALLOW_SEMANTICS`.
3. Golden wire fixtures: committed (payload → stdout, exit) for every agent × scenario
   event (`examples/scenarios.py`) × the six outcomes of
   `test_decision_vocabulary.py:34-41`, captured from the pin's adapters *before* any
   engine lands; the migration's empty-diff proof.
4. The thirteenth vendor: a synthetic fixture vendor added by config alone exercises
   the no-code promise end to end (claims, parse, respond, hook_config, bundle).
5. Bundle equivalence: generated runtime == library, per vendor, over the golden set.
6. Mutation checks on the schema validator itself (a validator nobody has watched fail
   proves nothing — org-plan `worker-protocol.md` discipline).

## 6. Decomposition

Waves sized to land green independently; adapters are deleted only when their family
engine carries their full conformance load with an empty golden diff.

| wave | delivers | done when |
| :--- | :--- | :--- |
| D1 | Golden wire fixtures (§5.3) captured from today's adapters + replay test | suite green at the pin's behaviour; fixtures committed |
| D2 | `data/vendors/` schema + validator + all 12 entries written (unused by runtime yet); consistency tests §5.1–2 | schema tests green; entries recount against adapter constants |
| D3 | **F1 engine** (`hook_json`: accessor, marker claims, G1–G3 renderers, degrade tables) behind `adapters.get`; claude_code, vscode_copilot, codex_cli, kimi_code, devin migrated; their 5 modules deleted | per-adapter suites + golden diff empty for all 5; bundler still splices legacy-style for others |
| D4 | **F2 engine** (`flat_decision`: G1 only); gemini_cli, junie, tabnine, grok migrated and deleted | same bar, 4 vendors |
| D5 | Singleton dialect modules (cursor, windsurf, antigravity) rebased onto the shared accessor/claims machinery + config entries; shape-inference stays local code | same bar, 3 vendors |
| D6 | Bundler emits engine + inlined `VENDOR` config (§4); equivalence + byte-stability tests; legacy splice paths deleted; the thirteenth-vendor test | all §5 new tests green; README/AGENTS.md "adding an agent" updated to the config path |

Ordering note: D3 before D4 follows the brief's largest-family-first suggestion; F1 is
also the family with the strongest live evidence behind its wire shapes
(`matrix_evidence.py:14-56,151-173`), which is what makes freezing its wire in D1
trustworthy. If implementation prefers proving the machinery on F2's single grammar
first, D3/D4 swap cleanly — they share only D1+D2.

## 7. Open questions carried as hypotheses

- **[h]** Bundle size estimates in §4 are composition arithmetic, not measurements;
  D3 should publish real numbers next to them.
- **[v]** (was [h]) The `reject_probes: ["looks_like_claude_code"]` device (named engine
  predicates referenced from config) is the narrowest crack in the code/config line;
  if D2 finds more than ~3 named probes are needed, that is evidence the line is drawn
  wrong, and the design should be revisited rather than the list grown. **Answered by D2**:
  exactly one named probe (`looks_like_claude_code`), used by `gemini_cli` and `devin` --
  well inside the budget (`tests/test_vendor_config.py::
  test_reject_probes_stay_under_the_three_probe_budget`). The design stands as written.
- **[h]** vscode_copilot's dual-casing may be cleaner as two config entries sharing a
  family than one entry with paired key chains; decide in D3 with the fixtures open.
- **[v]** (was [h]) PR #89's loader restores every JSON array as a tuple; `fields` chains
  here are order-sensitive lists and unaffected, but D2 must confirm the loader's
  tuple-restore doesn't collide with schema types. **Answered by D2**: a tuple preserves
  the exact sequence its JSON array was written in, so the restore is order-safe; nothing
  in `vendor_config.py` or its tests ever compares one of these tuples against a list
  literal with `==` (`tests/test_vendor_config.py::
  test_loader_tuple_restore_preserves_field_chain_order`).
