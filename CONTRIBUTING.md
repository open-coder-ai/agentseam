# Contributing to agentseam

## What this project is

A primitives layer: it owns the differences between coding agents so tools built on
top do not have to. Most contributions are one of three shapes:

1. **A new agent adapter** — the common case, and deliberately cheap.
2. **A matrix correction** — a vendor changed behaviour, or a row is wrong.
3. **A new primitive or event** — rarer; changes the contract, so it needs discussion first.

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
src/agentseam/adapters/<agent>.py     AGENT, claims(), parse(), respond(),
                                      hook_config(), CONFIG_PATH
src/agentseam/matrix.py               one MATRIX row, incl. a `verified` record
tests/test_adapters.py                fixtures using the vendor's REAL payloads
```

Payload fixtures must come from primary sources — the vendor's own docs, their example
repo, or a captured live run — and the `verified` record must say which. Shapes invented
from a blog post are how a hook silently stops firing six months later.

Adding an agent must not require touching `contract.py`, `dispatch.py`, or any consumer.
If it does, the abstraction is wrong; say so in the PR and we fix the abstraction.

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

## Review policy

Adapters and the matrix get the slow path: they decide what downstream tools may claim.
Expect reviewers to check payload shapes against the cited source rather than trusting
the diff.
