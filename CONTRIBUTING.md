# Contributing to agentseam

## What this project is

A primitives layer: it owns the differences between coding agents so tools built on
top do not have to. Most contributions are one of three shapes:

1. **A new agent adapter** — the common case, and deliberately cheap.
2. **A matrix correction** — a vendor changed behaviour, or a row is wrong.
3. **A new primitive or event** — rarer; changes the contract, so it needs discussion first.

New here? The [seeded good-first-issue
list](https://github.com/open-coder-ai/agentseam/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
collects small, scoped starting points — a narrow adapter gap, a missing evidence report —
sized for a first pull request.

## The rule that overrides preference

**Never claim an enforcement a vendor cannot deliver.** `matrix.enforcement_level()`
is the authority, and a PR that widens a claim without a mechanism behind it will be
asked for the mechanism instead. Concretely:

- If an agent blocks but fails *open* on hook error, that is `best-effort`, not `enforced`.
- If an event fires after the action, that is `detect`. Say so; do not imply prevention.
- If an agent has no hook surface at all (Zed, Aider today), the matrix row is empty.
  An empty row is a feature — it is what stops a downstream tool lying to its users.

## Adding an agent adapter

```
src/agentseam/data/vendors/<agent>.json   the vendor entry: family, events, claims,
                                          fields, verdicts, hook_entry (schema.json beside it)
src/agentseam/adapters/__init__.py        the agent's name added to _CONFIG_DRIVEN
src/agentseam/data/matrix.json            one MATRIX row, incl. a `verified` record
tests/test_adapter_<agent>.py             fixtures using the vendor's REAL payloads
tests/fixtures/golden/<agent>.json        golden wire fixtures (tools/capture_fixtures.py)
```

An agent whose grammar or shape inference no existing family speaks also gets a small
family module — the config/code line is `docs/design/dialect-families.md` §3.1.

Payload fixtures must come from primary sources — the vendor's own docs, their example
repo, or a captured live run — and the `verified` record must say which. Shapes invented
from a blog post are how a hook silently stops firing six months later.

Adding an agent must not require touching `contract.py`, `dispatch.py`, or any consumer.
If it does, the abstraction is wrong; say so in the PR and we fix the abstraction.

## The ladder

Contributions here get larger in one direction, and you can stop at any rung:

1. **An evidence report** — run a probe, paste what actually happened. No code, and it is the
   most useful thing a newcomer can do, because a claim nobody re-ran is just a claim.
2. **An eval case** — a input that should be caught, or should not be, with the expected
   verdict. This is how a guard stops regressing.
3. **A policy** — a rule plus the mechanism that enforces it, honestly labelled as enforced or
   advisory.
4. **An adapter** — support for one more agent, matched to what that agent's hooks can really do.
5. **Review** — reading someone else's evidence and saying whether it holds.

**Becoming a maintainer:** three merged pull requests earns triage rights — labelling, closing
duplicates, and asking for the evidence a report is missing. Nobody is asked to commit to more
than they want to.

This repo's own CI is the filter for low-effort or machine-generated pull requests, not a human
gatekeeper: the `dco` job rejects any commit missing a DCO sign-off, and `no-private-data` scans
every commit message and PR body for exactly the kind of thing a careless tool leaves behind. A
PR that cannot say what it checked will not pass, whoever or whatever wrote it.

Rung one is the section immediately below. Running the capture probe for one agent you already
have installed and pasting the report is the single best on-ramp into this project — *Contributing
evidence* covers what the probes can and cannot see and where to send what you find.

## Contributing evidence (you do not need to write code)

Twelve of sixteen matrix rows rest on vendor documentation rather than on anyone watching
the agent run. If you have one of those agents installed, you can close that gap for
everyone in about two minutes — and you are, by definition, better placed to than a
maintainer who does not hold that licence.

**Payload shapes** — what the agent actually sends:

```bash
python3 tools/capture.py detect
python3 tools/capture.py install --agent <agent>
# ...use the agent normally for a minute...
python3 tools/capture.py report
python3 tools/capture.py uninstall --agent <agent>
```

**Enforcement** — whether `deny` blocks, and what happens when a hook dies:

```bash
python3 tools/experiment.py run --agent <agent> --report \
    --agent-version <version> --reporter @yourhandle > report.json
```

Open an issue with the **Evidence report** template and paste the result.

A few things worth knowing before you run either:

- **The capture probe always allows.** It records and gets out of the way, so it cannot
  break a session. The experiment probe is the opposite — it denies, crashes and stalls
  on purpose — so it only ever runs in a throwaway directory the harness creates and
  removes. Never point it at a config you work in.
- **Payloads are reduced to shape before anything touches disk.** Keys and types survive;
  values become markers like `<str:41>`. `tests/test_capture_kit.py` asserts this by
  running the real probe rather than by reading its source.
- **A result that contradicts the matrix is the most valuable thing you can send.** We are
  not collecting confirmations. If your run says an agent fails closed where we claim it
  fails open, that is a row we are getting wrong in public.
- **Nothing captured is worthless.** A hook that never fires is a finding: it means the
  config path or format is wrong for your version, which is exactly what documentation
  does not tell you. Report it with the agent's version.
- **Reports say how they were obtained, and cannot overstate it.** A run against the
  `reference` driver is the vendor's documentation made executable, not a measurement, and
  the schema refuses to let it claim `live-run`. `python3 tools/verify_report.py
  report.json` shows you what a maintainer will see.

Evidence carries the reporter's handle. Age and version drift are displayed rather than
hidden — see `agentseam matrix --evidence`. A row that says "verified against 3.17.8, 87
days ago" is more useful than one that silently implies it is current.

### When a drift issue names your agent

A weekly check (`tools/watch_versions.py`) opens an issue titled `evidence: <agent>
<version> — re-witness wanted` when an agent has shipped since its evidence was taken. That
issue is a work order for whoever has the agent installed — the same two-minute loop above,
`--record` added:

```bash
python3 tools/experiment.py run --agent <agent> --event <gate> \
    --driver "<your headless CLI invocation>" \
    --agent-version <version> --record --reporter @yourhandle
```

This freezes what you saw into `data/recordings/<agent>@<version>.json`, which
`--driver recorded` then replays in CI instead of anyone re-running a real agent every
time. Submit it the same two ways as any other evidence: a PR adding that file (plus the
`data/matrix.json` per-claim `test` pointers it backs), or the **Evidence report** template
with the recording pasted in. A run against `reference` or `recorded` never counts as the
re-witness the issue is asking for — only a real agent does.

## Local checks

```bash
pip install -e ".[dev]"
git config core.hooksPath .githooks   # once per clone -- see below
pytest -q                 # the suite
ruff check . && ruff format --check .
agentseam matrix          # eyeball the honesty table
```

### The generated examples refresh themselves

`examples/generated/` is produced from the real code paths, so a change to an adapter or to
the matrix invalidates it. Enabling `core.hooksPath` puts the regenerated pages in the same
commit as the change that caused them, which is where they belong -- reviewing a behaviour
change next to its effect on every vendor is most of the value.

The hook only fires for commits touching `src/agentseam/` or the generator's own inputs, so
a docs commit stays untouched. If you skip it, or commit with `--no-verify`, CI catches the
drift and prints the diff.

```bash
python3 examples/generate.py           # refresh by hand
python3 examples/generate.py --check   # what CI runs
```

Hooks are not cloned and `--no-verify` skips them, so this is the convenience and the CI
job is the guarantee. Both run the same script, for the reason the stdlib-only check does:
a second implementation of a check drifts from the first and ships a red pipeline.

## Constraints that are not negotiable

- **Stdlib only** in the runtime path. Adapters get vendored as single files into other
  projects; a third-party import breaks exactly the consumers this library exists for.
- **300-line file budget** (`tests/test_repo_standards.py`). The remedy is splitting by
  activity, not raising the number.
- **No telemetry, no network calls** at runtime. This code sits in the path of every tool
  call a developer's agent makes.

## Sign your commits (DCO)

This project uses the [Developer Certificate of Origin](https://developercertificate.org/)
rather than a CLA: a one-line trailer certifying you have the right to contribute the
change under Apache-2.0.

```bash
git commit -s -m "feat(adapters): add gemini-cli adapter"
```

CI checks every commit on a PR. Forgot one?

```bash
git commit --amend -s --no-edit && git push --force-with-lease
```

## Before you change anything structural

Read [ARCHITECTURE.md](ARCHITECTURE.md). It is hand-written and covers the reasoning the
code cannot state for itself: the layering boundary, why `UNKNOWN` sits outside the event
vocabulary, why detection must never guess between two adapters, and what each coverage
tier is defending against. If your change alters any of that, update the document in the
same PR — nothing regenerates it.

## Review policy

Adapters and the matrix get the slow path: they decide what downstream tools may claim.
Expect reviewers to check payload shapes against the cited source rather than trusting
the diff.
