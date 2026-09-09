<div align="center">
  <img src="https://raw.githubusercontent.com/open-coder-ai/agentseam/main/docs/assets/logo.svg" alt="agentseam mark: five uneven vendor lines converging through a seam into five even lines" width="104">
  <h1>agentseam</h1>
  <p><b>One handler API over every coding agent's hooks, instruction files, plugins and config — with a matrix of what each agent can actually enforce.</b></p>

[![CI](https://github.com/open-coder-ai/agentseam/actions/workflows/ci.yml/badge.svg)](https://github.com/open-coder-ai/agentseam/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/agentseam)](https://pypi.org/project/agentseam/)
[![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/open-coder-ai/agentseam/badge)](https://scorecard.dev/viewer/?uri=github.com/open-coder-ai/agentseam)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
</div>

<p align="center"><img src="https://raw.githubusercontent.com/open-coder-ai/agentseam/main/docs/assets/demo.gif" width="760" alt="Terminal recording: agentseam install all wires one handler into every coding agent's own hook config in a single command. The output grades each agent honestly -- best-effort for eleven of them, the stronger enforceable gate for Cursor -- and says nothing at all for aider, Copilot CLI, Replit and Zed, which have no hook surface to wire."></p>

Every coding agent invented its own hook system: different event names, payload shapes,
ways to say "no", config files. So every guardrail, cost tracker or audit log gets written
once per agent — or targets one agent and stops there. agentseam is the layer underneath:
one normalized event, one `Decision`, and an explicit, verified map of what each agent can
do with it. When an agent cannot enforce something, agentseam says so instead of installing
a hook that silently does nothing. Every outcome a handler can return — `allow`, `deny`,
`escalate` (alias `ask`), `transform` (alias `rewrite`), `warn`, `vouch` — degrades honestly
on an agent that cannot express it, never silently. Agents are not equally capable, and
pretending otherwise is how a "policy" silently fails; the capability matrix below is data,
not marketing.

## Quick start

```bash
mkdir demo && cd demo && git init -q
cat > my_handler.py << 'EOF'
from agentseam import run, Decision

def handler(event):
    if event.event == "pre_tool" and "AKIA" in (event.content or ""):
        return Decision.deny("no AWS keys in memory files")
    return Decision.allow()

run(handler)
EOF
pip install agentseam
agentseam install all "python3 my_handler.py" --events pre_tool --repo .
```

That one handler now runs in Claude Code, Cursor, VS Code Copilot, Codex, Gemini CLI,
Windsurf and six more — and the install output tells you which agents get *best-effort*
blocking, which get the stronger *enforceable* gate (Cursor, today), and which do not
appear in the output at all because they have no hook surface to wire (aider, Copilot CLI,
Replit, Zed). Nothing here is emulated: `install` writes real per-agent config files into
`--repo`, the same files Claude Code, Cursor and the rest read on their next run, and
`uninstall` removes only the entries agentseam itself wrote.

## What each agent can actually do

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/open-coder-ai/agentseam/main/docs/figures/matrix-dark.svg">
  <img alt="Capability matrix: 16 coding agents by 12 lifecycle events, graded from src/agentseam/matrix.py. Of 192 cells: 2 are enforceable, 33 best-effort, 56 detect, and 101 none. Zero cells anywhere are graded enforced -- eleven agents reach only best-effort at pre_tool, Cursor alone reaches enforceable there, and aider, Copilot, Replit and Zed have no hook surface at pre_tool at all." src="https://raw.githubusercontent.com/open-coder-ai/agentseam/main/docs/figures/matrix-light.svg" width="760">
</picture>

*192 cells generated from `src/agentseam/matrix.py`: 101 none, 56 detect, 33 best-effort, 2 enforceable, 0 enforced.*

| Level | Meaning |
|---|---|
| enforced | the agent blocks, and fails closed if the hook dies — no agent is graded here at `pre_tool` today |
| best-effort | it blocks, but fails *open* (a crashed hook allows) |
| detect | observable after the fact only; prevention is not available |
| enforceable | it blocks and *can* be told to fail closed, but doesn't by default |
| none | no hook surface at all |

A row is only claimed when a `verified: {basis, version, date}` record backs it. No row
asserts a capability nobody has verified — run `agentseam doctor` to see what is wired on
this machine and flag rows that haven't been re-verified in 90 days. Grading never exceeds
evidence: a `vendor-docs` row cannot back `enforced`, however its cell reads, because
`enforcement_level()` caps every grade by what its own basis can actually support.

## Supported agents

`unadapted` is a fourth, deliberately separate state from `none`: agentseam has no hook
adapter for that agent yet — a claim about *us*, not about the agent, since it still
receives instruction files and simply cannot have its tool calls gated here. A
`Decision.transform(...)` on an agent that cannot transform degrades to `escalate`, never
to a silent pass-through.

| Agent | What it enforces | Config file | Verified |
|---|---|---|---|
| Claude Code | block + rewrite | `.claude/settings.json` | live-run · 2026-09-07 |
| VS Code Copilot | block + rewrite | `.github/hooks/*.json` | live-run-partial · 2026-08-28 |
| Cursor | block + rewrite (all tools, fail-open by default) | `.cursor/hooks.json` | live-run-partial · 2026-08-27 |
| Gemini CLI | block + rewrite (fail-open) | `.gemini/settings.json` | vendor-source · 2026-08-28 |
| OpenAI Codex CLI | block + rewrite (fail-open) | `.codex/hooks.json` | live-run-partial · 2026-08-28 |
| Windsurf | block via exit code only; no file-write event | `.windsurf/hooks.json` | third-party-install · 2026-08-26 |

<details>
<summary>10 more agents</summary>

| Agent | What it enforces | Config file | Verified |
|---|---|---|---|
| Devin | block + rewrite (fail-open) | `.devin/hooks.v1.json` | vendor-docs · 2026-08-26 |
| Grok CLI | block on PreToolUse only (fail-open) | `.grok/hooks/agentseam.json` | vendor-docs · 2026-08-26 |
| Antigravity | block, and can refuse to let the agent stop (fail-open) | `.agents/hooks.json` | vendor-docs · 2026-08-26 |
| Kimi Code CLI | block on 3 of its 20 events (fail-open) | `~/.kimi-code/config.toml` | vendor-docs · 2026-08-26 |
| Junie CLI | block + ask + rewrite, all native (fail-open) | `~/.junie/config.json` | vendor-docs · 2026-08-26 |
| Tabnine CLI | block on 6 of its 11 events, incl. post-tool (fail-open) | `.tabnine/agent/settings.json` | vendor-docs · 2026-08-26 |
| Zed | no hook surface at all — instruction files only | — | vendor-docs · 2026-08-26 |
| Aider | no hook surface at all — instruction files only | — | vendor-docs · 2026-08-26 |
| Replit | no hook surface found in its docs — instruction files only | — | vendor-docs · 2026-08-26 |
| Copilot CLI marketplace bundle | packaging identity only — dispatches through the VS Code Copilot adapter, not a hook surface of its own | — | vendor-docs · 2026-08-29 |

</details>

Of the 12 agents that claim `pre_tool` at all, 4 — Claude Code, Codex CLI, Cursor, VS Code
Copilot — rest on a live run against the real agent; the other 8 rest on documentation or a
third-party install, not on a live run. Run `agentseam matrix --evidence` before you trust
any row you didn't witness yourself.

## What it is for

Not just guardrails. Anything that wants to watch or shape an agent's life:

| | |
|---|---|
| **Observability** | one JSONL/OTel stream across every agent in the repo (`examples/event_log.py`) |
| **Notifications** | desktop notification on stop or prompt (`examples/notify.py`) |
| **Cost tracking** | token/cost meters that work regardless of which agent ran |
| **Guardrails** | secrets, memory governance, destructive-command blocks |
| **Process gates** | TDD enforcement, "tests before push" |
| **Context injection** | inject memory/instructions at session start |

## Instructions and permissions across agents

Multi-agent repos hand-maintain a drawer of near-identical files — CLAUDE.md, AGENTS.md,
`.cursor/rules/*`, `.github/copilot-instructions.md`, GEMINI.md, `.windsurfrules`,
`codex.md` — and they drift.

```bash
agentseam instructions --text "Prefer pnpm. Tests live beside source."
```

```
updated   AGENTS.md
created   CLAUDE.md
created   .junie/guidelines.md
...
covered by AGENTS.md: codex_cli, copilot, cursor, gemini_cli, kimi_code, vscode_copilot, windsurf, zed
```

16 agents reached with 9 files written, because 8 of them read `AGENTS.md` natively and a
second copy would only drift. Content is written as a marker-delimited block, so anything a
human wrote in those files is preserved untouched, and `instructions --list` shows what a
repo is already telling its agents without writing anything.

Permissions are the same story with sharper edges: every agent has a settings file with an
allow/deny model, and no two of them are the same kind of object. Claude Code evaluates an
ordered rule list. Gemini CLI keeps tool-name allowlists. Codex runs a Starlark program over
command prefixes. VS Code holds a map of auto-approve patterns. They do **not** have the
same expressive power.

```bash
agentseam permissions --rule 'deny:shell:curl *' --rule 'allow:shell:npm test'
```

```
# claude_code -> .claude/settings.json
{"permissions": {"allow": ["Bash(npm test)"], "deny": ["Bash(curl *)"]}}

# vscode_copilot -> .vscode/settings.json
{"chat.tools.terminal.autoApprove": {"npm test": true}}
# unrepresentable: Rule('deny', 'shell', 'curl *') -- this map has no deny: setting a
# pattern false withholds auto-approval but still lets a human approve the command
```

VS Code has no deny — the tool refuses rather than pretends. Rendering a "deny" there would
hand back a guardrail that stops nothing, so agentseam returns the rule unrendered with the
reason instead, and the command exits non-zero. Put it in CI and you find out that your
policy doesn't survive the trip to an agent *before* you rely on it.

The reasons distinguish two things that are easy to blur: an agent whose permission system
*provably exists* but whose schema nobody has read yet (Antigravity, Devin, Grok and Kimi
Code each prove it through their own hook events) versus one where nothing is established at
all. A missing hook surface is never recorded as a missing permission model either — Aider
and Zed expose no hooks, which says nothing about what their config files can restrict.
Every agent the matrix knows appears in `agentseam permissions` output, either with a
recorded model or named with the reason there isn't one, and a test enforces that the two
sets add up to the matrix exactly — a silently absent agent would read as "nothing to say
here" when the truth is "nobody looked".

## Verify a claim against your own agent

Claude Code's row rests on a full live run; Codex CLI, Cursor, and VS Code Copilot each rest
on a partial one. If you have another of these agents installed, an hour turns its row from
"the vendor says so" into evidence:

```bash
python3 tools/capture.py detect
python3 tools/capture.py install --agent cursor
# ... use the agent for a minute ...
python3 tools/capture.py report
python3 tools/capture.py uninstall --agent cursor
```

The probe always allows, so it cannot interfere with real work, and payloads are reduced to
shape before anything touches disk — keys and types survive, values do not. A different
probe, `tools/experiment.py`, does the opposite on purpose: it denies, crashes and stalls,
so it only ever runs in a throwaway directory a harness creates and removes — never point it
at a config you work in. See [tools/VERIFY.md](tools/VERIFY.md).

## Contributing

The most valuable contribution needs no code. Most rows in the matrix above rest on vendor
documentation rather than on anyone watching the agent run. If you have one of those agents
installed, one command reports what your version actually does, and the result becomes a
`verified` record with your handle on it:

```bash
python3 tools/experiment.py run --agent <agent> --report \
    --agent-version <version> --reporter @yourhandle > report.json
```

Paste it into an [evidence report](https://github.com/open-coder-ai/agentseam/issues/new?template=evidence-report.yml).
A result that contradicts the matrix is the one we most want: it is a row we are getting
wrong in public. The walk-through, including the capture probe for payload shapes, is in
[CONTRIBUTING.md](CONTRIBUTING.md#contributing-evidence-you-do-not-need-to-write-code).

Other ways in:

- **An adapter for an agent that is missing.** Goose, Crush and OpenCode are researched and
  unbuilt; each is a config entry plus a matrix row. Start from the
  [adapter request](https://github.com/open-coder-ai/agentseam/issues/new?template=adapter_request.md) template and
  [CONTRIBUTING.md](CONTRIBUTING.md#adding-an-agent-adapter).
- **A matrix correction.** A row that claims more than the agent does is the bug this project
  exists to prevent; the [matrix correction](https://github.com/open-coder-ai/agentseam/issues/new?template=matrix_correction.md)
  template is for exactly that.
- **Bugs and docs.** Issues and PRs welcome — start with a
  [good first issue](https://github.com/open-coder-ai/agentseam/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)
  if you want a bounded one. `pytest -q` and `ruff check .` are the whole local loop, the
  runtime path stays stdlib-only, and every commit is signed off (`git commit -s`).

Adding an adapter must never require touching `contract.py`, `dispatch.py`, or any consumer
— if it does, the abstraction is wrong, and the PR should say so rather than route around it.
Evidence carries the reporter's handle, and a weekly check opens an issue naming any agent
that has shipped since its evidence was taken (`evidence: <agent> <version> — re-witness
wanted`) — that issue is a work order for whoever has the agent installed.

More: [Bundles](docs/bundles.md) · [Design](docs/design.md) ·
[per-vendor examples](docs/vendor-examples.md) · [ARCHITECTURE.md](ARCHITECTURE.md).

## Part of open-coder-ai

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="https://raw.githubusercontent.com/open-coder-ai/agentseam/main/docs/figures/family-dark.svg">
  <img alt="Layered diagram of the open-coder-ai family: agentseam is the foundation across the bottom, chock sits on it, chock-catalog feeds chock and generates four plugin repositories, chock-threat-intel feeds the catalog, and context-report runs as a verification arm beside all of them." src="https://raw.githubusercontent.com/open-coder-ai/agentseam/main/docs/figures/family-light.svg" width="800">
</picture>

| | |
|---|---|
| [agentseam](https://github.com/open-coder-ai/agentseam) | the primitives — one handler API and a verified capability matrix across 16 agents |
| [chock](https://github.com/open-coder-ai/chock) | the compiler — one policy into git hooks, CI gates and native pre-tool hooks |
| [chock-catalog](https://github.com/open-coder-ai/chock-catalog) | the policies — 39, each labelled enforced or advisory, with replayed evals |
| [context-report](https://github.com/open-coder-ai/context-report) | the evidence — a signed report of whether an agent artifact actually works |
| [chock-threat-intel](https://github.com/open-coder-ai/chock-threat-intel) | the threat ledger the catalog's policies answer to |
| chock-{claude,cursor,copilot,codex}-plugins | the catalog, packaged for each agent's plugin format (generated) |
| chock-quickstart · chock-example | template repos: what `chock init` leaves behind, and a full adoption |

Apache-2.0.
