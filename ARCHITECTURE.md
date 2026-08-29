# Architecture

This document explains **why agentseam is shaped the way it is**. The README shows what it
does; the source shows how. Neither says what the shape is defending against, and that is
the part a new contributor keeps rediscovering the expensive way.

Written by hand and maintained by hand. It goes stale when nobody updates it, which is the
honest trade for the fact that a generator cannot write the *why*.

---

## 1. The layering principle

agentseam is one layer of three, and the split is the whole design:

| layer | what it holds | what it must never hold |
|---|---|---|
| **agentseam** | primitives — mechanism | policy, opinion about what should be blocked |
| **chock** | the policy engine — decides | vendor knowledge |
| **chock-catalog** | policy content — rules, catalogs | code |

agentseam knows how to talk to twelve vendors and nothing about what *should* happen. Ask
it whether a command is dangerous and there is no answer here; ask it whether Cursor can
block that command before it runs, and there is.

The reason for the boundary is failure locality. When a policy is wrong, the fix belongs in
one repo and ships to every agent at once. When a vendor changes its hook payload, the fix
belongs in one adapter module and no policy changes. Fuse the two — as every tool that
grows organically eventually does — and a Cursor payload change becomes a policy review.

**Practical rule:** if a change requires knowing what a rule *means*, it does not belong in
this repo. If it requires knowing what a vendor sends, it does not belong in the other two.

---

## 2. The four primitives

Everything here is one of four things an agent-facing tool needs and would otherwise build
per vendor. They are not a taxonomy invented up front; they are what was left after
enumerating what chock had to write twelve times.

1. **Hooks** — lifecycle events, normalized, plus the honest capability record.
   `contract.py`, `dispatch.py`, `install.py`, `bundler.py`, `adapters/`. `bundler.py` is
   this primitive rendered standalone: `bundle(agent)` assembles `contract.py` plus one
   adapter (plus whatever it transitively needs) into a single stdlib-only file with no
   `import agentseam`, for a consumer that vendors the runtime into a repo that may never
   install this package — the same normalize-stdin-to-vendor-dialect plumbing `dispatch.py`
   runs in-process, composed at the source level with `ast` rather than copy-pasted, so it
   cannot drift from the adapter it was built from.
2. **Instruction files** — one body of text, every agent's drawer of near-identical
   markdown files. `instructions.py`.
3. **Plugin / skill packaging** — one bundle, each agent's layout. `packaging*.py`.
4. **Config & permissions** — one rule set, four incompatible permission languages.
   `permissions*.py`.

They share one property, which is why they are one library: each is a place where the
vendors have chosen mutually incompatible representations of the *same* concept, and each
has cases where the translation is lossy. The lossy cases are handled the same way
everywhere — see §5.

---

## 3. The contract boundary

`contract.py` is L0. It knows no vendor, imports nothing but the future, and is embedded
verbatim into rendered single-file adapters. Three things live there:

**A 12-event canonical vocabulary.** Vendor names map *onto* it; adapters own the mapping.
A vendor lacking an event simply has no matrix row for it. That absence is the coverage
floor, said out loud.

**`Event`, which always keeps `raw`.** Normalizing is a convenience, not a cage. A consumer
needing something vendor-specific reaches through rather than being blocked by our
vocabulary — otherwise every gap in the vocabulary becomes a fork.

**`Decision` — allow / deny / ask / rewrite.** Four outcomes, because those are the four
things the union of vendors can express. Not every vendor can express all four; see §5.

### `UNKNOWN` is deliberately outside `EVENTS`

When a vendor sends something an adapter has no mapping for, the answer is `UNKNOWN`, and
`UNKNOWN` is not a member of `EVENTS`. A handler matching on the vocabulary can therefore
never match it by accident.

Five adapters used to do the intuitive thing instead — fall back to the nearest canonical
event. That reports an unknown event as `pre_tool` and invites a guardrail to evaluate a
pre-tool policy against something that is not one. New vendor events appear without notice;
being told is the only safe outcome. The dispatcher does not call the handler at all for
these: it allows, silently, and still returns the event so a caller can log the surprise.

---

## 4. Adapters own all vendor knowledge

An adapter is a module with `AGENT`, `CONFIG_PATH`, `claims()`, `parse()`, `respond()`, and
`hook_config()` — the six the interface test requires. Adding an agent is a module plus a
matrix row: no consumer changes, no dispatcher changes, no `if agent == ...` anywhere.

`test_every_adapter_implements_the_interface` and `test_every_adapter_has_a_matrix_row`
keep that true, because a rule this load-bearing erodes the first time somebody is in a
hurry.

### Detection collisions are this repo's characteristic bug

`adapters.detect(raw)` identifies the agent from an unlabelled payload. It returns a name
only when **exactly one** adapter claims it — never a guess between two.

That rule exists because the failure mode is silent and severe. Two adapters claiming one
payload means `detect()` returns `None`, the dispatcher treats it as an unrecognized shape,
and it **allows what it was installed to gate**. A guardrail that quietly stops guarding is
worse than one that was never installed, because somebody is relying on it.

Four of these have been found and fixed so far:

- Codex claiming on the presence of `model` — a field half the vendors send
- Gemini claiming any recognised event name, including `SessionStart`
- Claude Code claiming Devin, Kimi and Junie payloads that shared its field names
- VS Code widened to all of `EVENT_MAP`, which included PascalCase aliases, stealing Claude
  Code's payloads

The last one is the lesson worth keeping: **parse tolerance and identification are
different jobs.** An adapter should parse generously and claim narrowly. VS Code now claims
only on its lowercase names (`_CLAIMABLE`), while `parse()` still accepts both.

`test_no_two_adapters_claim_the_same_payload` runs every fixture against every adapter.
When you add an adapter, add fixtures — the test is only as good as its corpus.

---

## 5. Lossy translation is reported, never absorbed

Every primitive has cases the target cannot represent. The rule is the same in all four:
**hand back what could not be expressed, with a reason, and make the caller see it.**

- **Hooks.** `Decision.rewrite` on an agent that cannot rewrite degrades to `ask` — never
  to a silent pass-through, because the handler asked for the input to be *changed*. The
  reduction records `degraded_from` in evidence, so a second degradation downstream reports
  the right cause. Without it, a rewrite→ask→blocked chain gets reported as a failed
  confirmation request, and it was never a confirmation request.
- **Permissions.** `plan()` returns `(fragment, unrepresentable)`. VS Code's auto-approve
  map takes `false` for a pattern, which reads like a denylist and is not one: the command
  still runs once a human clicks through. Rendering a "deny" there hands you a guardrail
  that stops nothing, so the rule comes back unrendered and the CLI exits non-zero. Put it
  in CI and you find out your policy does not survive the trip *before* you rely on it.
- **Packaging.** Same shape, with agent-specific reasons. Gemini cannot take a `.mcp.json`
  — not because it lacks MCP, but because it declares servers in the manifest. "No MCP
  support" would be as wrong as saying nothing.
- **Install.** `install()` raises when asked to wire an event the adapter has no hook for,
  listing what it *can* wire. It used to write nothing and exit zero, which is how the
  matrix came to claim two events (`file_changed`, `instructions_loaded`) that no adapter
  had ever wired.

---

## 6. The honesty machinery

From SECURITY.md: **claim inflation is a security bug.** No capability claim without a
mechanism. That is a principle, and principles decay, so most of it is mechanical.

### Coverage tiers, and why there are six words

`matrix_terms.py` defines the vocabulary separately from the rows, because *deciding what a
word may mean* is a different activity from *claiming it about an agent* — and the words
are where the honesty actually lives. Each exists to stop a claim from being rounded up:

- **enforced** — blocks, and fails closed if the hook dies
- **enforceable** — blocks and *can* be told to fail closed, but does not by default
  (Cursor's `failClosed: true`). "best-effort" would understate a surface you can make
  airtight; "enforced" would claim a default that is not there. What a consumer may claim
  depends on how the hook was installed, so agentseam's installer asks for fail-closed on
  every gate it writes
- **best-effort** — blocks, but fails open
- **detect** — visible after the fact; prevention unavailable
- **none** — no hook surface (a claim about the **agent**)
- **unadapted** — no adapter here yet (a claim about **us**)

The last two are separate on purpose. Collapsing them would either slander an agent that
does expose hooks, or overstate our own coverage. Unadapted agents still receive
instruction files; they just cannot gate tool calls yet.

### `verified.basis` — what kind of evidence a row rests on

A closed vocabulary you can filter on: `live-run`, `vendor-source`, `vendor-docs`,
`third-party-install`, `inherited`. Free-text `method` says what was read; `basis` says what
class of claim it is.

**Only Claude Code's row is `live-run`; Cursor's is `live-run-partial`**, with the events
actually seen fire listed on the row. Two rows rest on the vendor's own source (Codex CLI,
VS Code Copilot) and one on a third-party installation (Windsurf); the remaining ten rest on
vendor documentation — a claim about what a vendor *says*, not an observation of what their
build does. `test_only_rows_actually_observed_claim_a_live_run` keeps that from
drifting upward, which is the direction claims drift.

There is a measured reason to distrust inherited rows specifically. No row carries that
basis today, because every row that once did has since been checked — and every one of them,
when checked against the vendor's own docs, turned out to claim **less** surface than the
agent actually has — Devin ("no pre-tool-use surface": false), Grok, Antigravity, Kimi Code (false in all
three clauses), Junie, Tabnine. Replit is the sole checked negative. `inherited` means
treat it as a lead, not a fact.

### Invariants that make absence loud

The recurring failure is not a wrong row — it is a **missing** one, which reads as "nothing
to say here" when the truth is "nobody looked". So:

- `recorded + unrecorded == matrix`, exactly, for both permissions and packaging, and no
  agent may be in both
- no `unrecorded` reason may be empty
- a missing *hook* surface is never recorded as a missing *permission* model (Aider and Zed
  expose no hooks; that says nothing about their config files)
- matrix events ⊆ wireable, and wireable ⊆ matrix events — in both directions, per agent

### Generated examples as a drift check

`examples/generated/` has a page per adapted agent with a section per hook, produced by
running the library. `generate.py --check` diffs the committed pages against fresh output
and CI fails on drift. A `.githooks/pre-commit` regenerates them when core or the generator
is staged, so the pages change in the same commit as the code.

An example nobody regenerates is a claim nobody checks. This works because the output is
**deterministic** — which is precisely why the same pattern does not extend to generated
prose, and why this file is hand-written.

---

## 7. Constraints, and what they cost

**Stdlib only in the runtime path.** Adapters get vendored as single files into projects
that cannot take a dependency. Enforced by AST scan. Cost: the stdlib cannot write TOML,
so a TOML-configured agent (Kimi Code) renders its own `[[hooks]]` text and install manages
it as a marker-delimited block, preserving every byte outside — the treatment instruction
files already use.

**300 lines per Python file.** The remedy is splitting **by activity**, never raising the
number. `matrix_data.py` hit the ceiling and became five files — terms, rows, gaps, notes,
evidence — each answering one question. Cost: more files, more imports.

> Split with `ast`, not regex. Regex-based splitting has mangled this codebase twice: once
> joining comment lines and stranding rows in `matrix_data.py`, once sweeping test bodies
> into `payloads.py`.

**Ownership-marked wiring.** Every entry install writes carries a `_agentseam` marker, so
uninstall removes exactly ours and re-install replaces rather than duplicates. A user's own
hooks in the same config are never touched. Borrowed from chock, which learned it the hard
way.

**No private data in tracked files.** Home paths, session ids, container scratch paths and
personal emails are a test, not a review habit. It has caught real mistakes — twice in one
change, in a redaction fixture of all places.

**Fail-open at the edges of our own knowledge.** An unrecognized payload allows silently; a
malformed one allows silently; an unmapped event allows silently. A dispatcher that failed
closed on payloads it did not know would break every agent it does not know — including the
ones released after this version shipped.

---

## 8. Where to start reading

| you want to | read |
|---|---|
| understand the whole runtime | `dispatch.py` (101 lines, top to bottom) |
| add an agent | any adapter + `matrix_data.py` + `tests/payloads.py` |
| know what an agent can really do | `matrix_terms.py`, then `matrix.py` |
| see a vendor's actual output | `examples/generated/<agent>.md` |
| turn a `vendor-docs` row into evidence | `tools/VERIFY.md` |

The fastest orientation is `examples/generated/claude_code.md` beside
`examples/generated/windsurf.md`: same situation, two vendors, and the difference between
`enforced` and a surface with no file-write event at all.
