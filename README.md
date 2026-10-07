<div align="center">

<p><img src="https://raw.githubusercontent.com/open-coder-ai/chock/main/docs/assets/readme/cover-agentseam.png" alt="Chock mark on a dusk-blue background." width="100%"></p>

</div>

# Teach your AI agent what not to do.

Open-source guardrails for AI coding agents: rules the agent reads, checks that run as it writes, and gates at commit and in CI. agentseam is the layer underneath: one handler API over every coding agent's hooks, instruction files, plugins and config, with a verified matrix of what each agent can actually enforce.

[chock](https://github.com/open-coder-ai/chock) · [chock-catalog](https://github.com/open-coder-ai/chock-catalog) · chock.sh (launching soon)

[![CI](https://github.com/open-coder-ai/agentseam/actions/workflows/ci.yml/badge.svg)](https://github.com/open-coder-ai/agentseam/actions/workflows/ci.yml) [![PyPI](https://img.shields.io/pypi/v/agentseam)](https://pypi.org/project/agentseam/) [![Python 3.9+](https://img.shields.io/badge/python-3.9%2B-blue.svg)](https://www.python.org) [![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE) [![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/open-coder-ai/agentseam/badge)](https://scorecard.dev/viewer/?uri=github.com/open-coder-ai/agentseam) [![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

agentseam is a stdlib-only Python library and CLI that turns every coding agent's own hook system into one normalized event and one `Decision`, and records, per agent and per lifecycle event, what that agent can really do with it. Write a guard once and `agentseam install` wires it into the agent's own config. When an agent cannot enforce something, agentseam says so instead of installing a hook that silently does nothing. Free and open source (Apache-2.0).

## Application security for the code your agents write

Coding agents already ask before they run a shell command. What they do not check is the code they write:
SQL injection in a Spring repository, a wildcard IAM grant, an MCP server pinned to `@latest`, a secret
written into agent memory. A guard at the agent's own `pre_tool` hook can refuse that write; a rule in the
prompt is forgotten when the context fills. Every agent invented its own hook system, so such a guard is
normally written once per agent, or for one agent and then stops. agentseam is the layer that makes it
one guard for 16 agents, and the matrix keeps the claim honest: a guard is only called enforced where
the agent can enforce it.

The Quick start handler is a guard. It reads the normalized `pre_tool` event and refuses content carrying
an AWS access key ID; agentseam turns each vendor's payload into that one event and turns the returned
`Decision` back into the vendor's own way of saying "no".

| A guard returns | What the agent does with it | Where it cannot |
|---|---|---|
| `Decision.deny(reason)` | refuses the tool call; the reason goes back to the agent | an agent with no `pre_tool` surface (aider, Copilot CLI, Replit, Zed) never asks |
| `Decision.escalate(reason)` | hands the call to the agent's own human-approval path | where the agent has no approval prompt at that gate, it blocks instead |
| `Decision.transform(new_input)` | runs the tool with a rewritten input (a redacted value, say) | degrades to `escalate`, never to a silent pass |
| `Decision.allow()` | lets it through | n/a |

The full outcome set is `allow`, `deny`, `escalate`, `transform`, `warn` and `vouch`; `ask` and `rewrite` are
deprecated aliases of `escalate` and `transform`. A handler that raises is turned into a refusal in the agent's own dialect. What agentseam
cannot fix is the host: if the hook process dies or times out, a best-effort agent runs the tool anyway.

**No LLM, no tokens.** agentseam makes no model call and `src/agentseam` imports no networking module
(checked with `grep -rn "import socket\|urllib\|http.client\|requests" src/agentseam`, empty at `104da73`).
A handler is your own local code: whatever it costs, it costs no tokens, and a refusal adds one short
reason to the agent's context. **Shift left:** the known classes are refused in the agent's own turn,
before they reach commit, review or CI.

## Install

chock is on PyPI, but the release there (0.15.2, 30 Sep 2026) is older than the engine this page describes. Install the frozen engine from its commit (Python 3.11 or newer):

```bash
pip install "chock @ git+https://github.com/open-coder-ai/chock@992711af4cf8d4fd9c4c861f10ef6e53374d75d7"
```

agentseam itself is `pip install agentseam` (Python 3.9 or newer, no dependencies); the Quick start below runs end to end.

### Two ways to adopt it

The guardrails built on agentseam, the [chock](https://github.com/open-coder-ai/chock) engine and the [chock-catalog](https://github.com/open-coder-ai/chock-catalog) policies, are adopted in two ways, and the chock.sh builder is a third.

| Way | For | What you get |
|---|---|---|
| **In your repository** | teams | commit gates enforced at commit and in CI; every clone runs `chock sync --repo .` once, because git never clones hooks |
| **In your coding agent, as plugins** | one person, no repo changes | in-agent checks, best-effort, failing open; not run in CI |
| **One Claude Code plugin from a selection** | trying it | the chock.sh builder (launching soon) gives a `chock install --selection '…' --apply` command |

In your repository:

```bash
chock init .
chock add <id> --ref <catalog commit> --verify-sha <sha256> --skip-compile   # once per policy
chock sync --repo . --ci
```

Commit the result. Plugin route: the five plugin repos are
[claude](https://github.com/open-coder-ai/chock-claude-plugins),
[cursor](https://github.com/open-coder-ai/chock-cursor-plugins),
[copilot](https://github.com/open-coder-ai/chock-copilot-plugins),
[codex](https://github.com/open-coder-ai/chock-codex-plugins) and
[devin](https://github.com/open-coder-ai/chock-devin-plugins); each README has its client's install lines.
Chock adds no new place your code goes: checks run where the agent writes. The agent still sends its
context to its own model provider; chock adds no additional destination.

## How it works

An adapter per agent owns three things: payload parsing, the response dialect and the config shape.
Adapters are data (`src/agentseam/data/vendors/<agent>.json`, validated against `schema.json`) plus a
small family module when a vendor speaks a new dialect. The matrix is data too, and
`matrix.enforcement_level(agent, event)` is the authority for every grade below.

*192 cells (16 agents by 12 events), from `matrix.enforcement_level()` run at `104da73`: 101 none, 55 detect, 34 best-effort, 2 enforceable, 0 enforced.*

| Level | Meaning | Agents at `pre_tool` today |
|---|---|---|
| enforced | the agent blocks, and fails closed if the hook dies | none |
| enforceable | it blocks and *can* be told to fail closed, but doesn't by default | 1: Cursor |
| best-effort | it blocks, but fails *open* (a crashed hook allows) | 11: Claude Code, VS Code Copilot, Codex CLI, Gemini CLI, Windsurf, Devin, Grok CLI, Antigravity, Kimi Code, Junie, Tabnine |
| detect | observable after the fact only; prevention is not available | 0 (55 cells at other events) |
| none | no hook surface at all | 4: aider, Copilot CLI, Replit, Zed |

A row is only claimed when a `verified: {basis, version, date}` record backs it. Run `agentseam doctor` to
see what is wired on this machine and flag rows not re-verified in 90 days. Grading never exceeds
evidence: `enforcement_level()` caps every grade by what its own basis can support, so a `vendor-docs`
row cannot back `enforced`. A pre-tool guard is one layer, not the whole defence: pair it with a git hook or
CI gate that the agent cannot skip.

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
Windsurf and six more. The install output tells you which agents get *best-effort*
blocking, which get the stronger *enforceable* gate (Cursor, today), and which do not
appear in the output at all because they have no hook surface to wire (aider, Copilot CLI,
Replit, Zed). Nothing here is emulated: `install` writes real per-agent config files, the same
files Claude Code, Cursor and the rest read on their next run, and `uninstall` removes only the
entries agentseam itself wrote. Most land under `--repo`; two do not, because the vendor reads
them from the user's home directory: Junie's `~/.junie/config.json` and Kimi Code's
`~/.kimi-code/config.toml`.

<p align="center"><img src="https://raw.githubusercontent.com/open-coder-ai/agentseam/main/docs/assets/demo.gif" width="760" alt="Terminal recording: agentseam install all wires one handler into every coding agent's own hook config in a single command. The output grades each agent honestly -- best-effort for eleven of them, the stronger enforceable gate for Cursor -- and says nothing at all for aider, Copilot CLI, Replit and Zed, which have no hook surface to wire."></p>

### Supported agents

`unadapted` is a fourth, deliberately separate state from `none`: agentseam has no hook
adapter for that agent yet, which is a claim about *us*, not about the agent, since it still
receives instruction files and simply cannot have its tool calls gated here. A
`Decision.transform(...)` on an agent that cannot transform degrades to `escalate`, never
to a silent pass-through.

| Agent | What it enforces | Config file | Verified |
|---|---|---|---|
| Claude Code | block + rewrite | `.claude/settings.json` | live-run · 2026-09-07 |
| VS Code Copilot | block + rewrite | `.github/hooks/*.json` | live-run-partial · 2026-08-28 |
| Cursor | block + rewrite (all tools, fail-open by default); `stop` returns a follow-up message | `.cursor/hooks.json` | live-run-partial · 2026-09-23 |
| Gemini CLI | block + rewrite (fail-open) | `.gemini/settings.json` | vendor-source · 2026-08-28 |
| OpenAI Codex CLI | block + rewrite (fail-open) | `.codex/hooks.json` | live-run-partial · 2026-08-28 |
| Windsurf | block via exit code only; no file-write event | `.windsurf/hooks.json` | third-party-install · 2026-08-26 |
| Devin | block + rewrite (fail-open) | `.devin/hooks.v1.json` | vendor-docs · 2026-08-26 |
| Grok CLI | block on PreToolUse only (fail-open) | `.grok/hooks/agentseam.json` | vendor-docs · 2026-08-26 |
| Antigravity | block, and can refuse to let the agent stop (fail-open) | `.agents/hooks.json` | vendor-docs · 2026-08-26 |
| Kimi Code CLI | block on 3 of its 20 events (fail-open) | `~/.kimi-code/config.toml` | vendor-docs · 2026-08-26 |
| Junie CLI | block + ask + rewrite, all native (fail-open) | `~/.junie/config.json` | vendor-docs · 2026-08-26 |
| Tabnine CLI | block on 6 of its 11 events, incl. post-tool (fail-open) | `.tabnine/agent/settings.json` | vendor-docs · 2026-08-26 |
| Zed | no hook surface at all; instruction files only | none | vendor-docs · 2026-08-26 |
| Aider | no hook surface at all; instruction files only | none | vendor-docs · 2026-08-26 |
| Replit | no hook surface found in its docs; instruction files only | none | vendor-docs · 2026-08-26 |
| Copilot CLI marketplace bundle | packaging identity only; dispatches through the VS Code Copilot adapter | none | vendor-docs · 2026-08-29 |

Of the 12 agents that claim `pre_tool` at all, 4 (Claude Code, Codex CLI, Cursor, VS Code
Copilot) rest on a live run against the real agent; seven of the other 8 rest on documentation
or a third-party install, and Gemini CLI on a read of the vendor's own source. None of those
eight rests on a live run. Run `agentseam matrix --evidence` before you trust any row you didn't witness yourself.

### Beyond security guards

Anything that wants to watch or shape an agent's life uses the same event stream:

| | |
|---|---|
| **Observability** | one JSONL stream across the agents an event set wires, ready to feed OTel or DuckDB (`examples/event_log.py`) |
| **Notifications** | desktop notification on stop or prompt (`examples/notify.py`) |
| **Cost tracking** | token and cost meters that work regardless of which agent ran |
| **Process gates** | TDD enforcement, "tests before push" |
| **Context injection** | inject memory or instructions at session start |

#### Instructions across agents

Multi-agent repos hand-maintain near-identical files (CLAUDE.md, AGENTS.md, `.cursor/rules/*`,
`.github/copilot-instructions.md`, GEMINI.md, `.windsurfrules`, `codex.md`) and they drift.

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

16 agents reached with 9 files written, because 8 of them read `AGENTS.md` natively and a second copy
would only drift. Content is a marker-delimited block, so anything a human wrote in those files is
preserved, and `instructions --list` shows what a repo already tells its agents without writing.

#### Permissions across agents

Every agent has a settings file with an allow/deny model, and no two are the same kind of object: Claude
Code evaluates an ordered rule list, Gemini CLI keeps tool-name allowlists, Codex runs a Starlark program
over command prefixes, VS Code holds a map of auto-approve patterns.

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

VS Code has no deny, so agentseam returns the rule unrendered with the reason and exits non-zero rather
than hand back a guardrail that stops nothing. Put it in CI and you learn that your policy does not survive
the trip to an agent *before* you rely on it. Every agent in the matrix appears in the output, with a
recorded model or the reason there is none; a test pins that the two sets add up to the matrix exactly.

#### Verify a claim against your own agent

Claude Code's row rests on a full live run; Codex CLI, Cursor and VS Code Copilot each on a partial one. If
you have another of these agents installed, an hour turns its row from "the vendor says so" into evidence:

```bash
python3 tools/capture.py detect
python3 tools/capture.py install --agent cursor
# ... use the agent for a minute ...
python3 tools/capture.py report
python3 tools/capture.py uninstall --agent cursor
```

The probe always allows, so it cannot interfere with real work, and payloads are reduced to shape
before anything touches disk: keys and types survive, values do not. `agentseam probe` does the opposite on
purpose (it denies, crashes and stalls), so it only runs in a throwaway directory a harness creates and
removes. See [tools/VERIFY.md](tools/VERIFY.md). A report's `driver` and `basis` fields say how it was
obtained: **witnessed** (a real vendor client, watched), **tested** (an automated check, no vendor client)
or **recorded** (a witnessed run replayed). `evidence_report.validate()` refuses a report that claims more
than its driver earned; [docs/coverage-gaps.md](docs/coverage-gaps.md) lists which gates are still open.

## What it stops

agentseam stops nothing by itself; it carries guards. The guards below ship in chock-catalog, which
`registry.yaml` at chock-catalog `f25f5a3` (policies unchanged since `9a64623`) lists as 71 policies: 35 enforced at commit, 11 in-agent (best-effort) and 25
advisory, with 4,280 eval cases of which 4,098 run automatically. Each policy is a manifest, labelled by tier.

| Class of flaw | Policy | Tier (`registry.yaml`) |
|---|---|---|
| Injection, XXE, SSRF, unsafe deserialization, path traversal and trust-all TLS in Java and Kotlin | [`java-security`](https://github.com/open-coder-ai/chock-catalog/tree/main/base/java-security) | enforced at commit |
| Host code execution, unpinned MCP servers, shell-reaching tools and approvals switched off in agent code and config | [`agentic-code-security`](https://github.com/open-coder-ai/chock-catalog/tree/main/agentic-security/agentic-code-security) | enforced at commit |
| Wildcard IAM grants | [`block-wildcard-iam`](https://github.com/open-coder-ai/chock-catalog/tree/main/agentic-security/block-wildcard-iam) | enforced at commit |
| MCP servers and agent components pinned to `@latest` | [`block-unpinned-agent-components`](https://github.com/open-coder-ai/chock-catalog/tree/main/base/block-unpinned-agent-components), [`verify-mcp-allowlist`](https://github.com/open-coder-ai/chock-catalog/tree/main/base/verify-mcp-allowlist) | enforced at commit |
| Unpinned GitHub Actions, packages outside an allowlist | [`pin-github-actions`](https://github.com/open-coder-ai/chock-catalog/tree/main/base/pin-github-actions), [`verify-dependency-exists`](https://github.com/open-coder-ai/chock-catalog/tree/main/base/verify-dependency-exists) | enforced at commit |
| Bidi and tag Unicode in source | [`block-invisible-unicode`](https://github.com/open-coder-ai/chock-catalog/tree/main/base/block-invisible-unicode) | enforced at commit |
| A change that strips an accessible name an element already had | [`no-a11y-regression`](https://github.com/open-coder-ai/chock-catalog/tree/main/base/no-a11y-regression) | enforced at commit |
| Hard-coded secrets and secret files | [`scan-secrets`](https://github.com/open-coder-ai/chock-catalog/tree/main/base/scan-secrets) | enforced at commit |
| Destructive commands, `--no-verify`, `curl \| sh`, edits to the agent's own guard config | [`block-destructive-commands`](https://github.com/open-coder-ai/chock-catalog/tree/main/base/block-destructive-commands), [`block-no-verify`](https://github.com/open-coder-ai/chock-catalog/tree/main/base/block-no-verify), [`block-curl-pipe-sh`](https://github.com/open-coder-ai/chock-catalog/tree/main/base/block-curl-pipe-sh), [`protect-agent-config`](https://github.com/open-coder-ai/chock-catalog/tree/main/base/protect-agent-config) | enforced at commit, or best-effort in-agent |

The in-agent tier is exactly the agentseam matrix: a catalog policy is never labelled stronger than
`enforcement_level()` grades the agent it runs in. No agent reaches `enforced`. Chock does not replace
code review, your SAST suite or a penetration test; it refuses known classes while the agent writes, so they are fixed before review.

## Guardrails, not guarantees

Tiers: `commit` is a git hook or CI gate that exits non-zero. `in-agent` is the agent's pre-tool hook: best-effort, and it fails open. `advisory` is rule text the agent reads. No agent reaches `enforced` today: 0 of 192 matrix cells are graded enforced. OWASP mappings are partial: 10 of 10 Agentic risks have a policy, 7 have a slice refused at commit, none is fully covered. The engine is frozen at the commit above. Chock does not stop every attack: it closes common, known entry points before they ship.

## FAQ for people and agents

**Does agentseam use an LLM?** No. It makes no model call and imports no networking module in `src/agentseam`.

**Does my code leave my machine?** agentseam adds no new place your code goes: handlers run locally in the
hook process. The agent still sends its context to its own model provider.

**Which agents does it work with?** 16 are in the matrix, 12 of them with a hook adapter; see Supported agents.

**How do I install it, through the repo or through plugins?** `pip install agentseam` for the library. For
guardrails, see Install above: the repository route (commit and CI) or the five plugin repos (in-agent).

**What does it cost?** Free and open source (Apache-2.0). A check costs no tokens; a refusal adds one short reason to the agent's context.

**Does it replace SAST or code review?** No. It catches known classes in the agent's turn; review, SAST and testing still run.

**Which OWASP and CWE items does it cover?** agentseam maps none itself. The catalog's OWASP mappings are
partial and labelled so; see chock-catalog `docs/coverage.md`.

## For tools and agents

- [`llms.txt`](llms.txt): a short machine-readable summary of this repo.
- [`src/agentseam/matrix.py`](src/agentseam/matrix.py) and [`src/agentseam/data/matrix.json`](src/agentseam/data/matrix.json): the capability matrix as data.
- [`src/agentseam/data/vendors/`](src/agentseam/data/vendors): one JSON entry per config-driven agent, validated by `schema.json`.
- [`registry.yaml`](https://github.com/open-coder-ai/chock-catalog/blob/main/registry.yaml): every catalog policy with its tier and eval counts.
- [`docs/coverage.md`](https://github.com/open-coder-ai/chock-catalog/blob/main/docs/coverage.md): catalog coverage, with partial mappings labelled.
- [`.claude-plugin/marketplace.json`](https://github.com/open-coder-ai/chock-claude-plugins/blob/main/.claude-plugin/marketplace.json): the Claude plugin marketplace.

## Part of open-coder-ai

The 13 public repositories:

| Repository | What it is |
| :--- | :--- |
| [agentseam](https://github.com/open-coder-ai/agentseam) | Core: One handler API over every coding agent. |
| [chock](https://github.com/open-coder-ai/chock) | Core: Author a policy once, enforce it on every agent. |
| [chock-catalog](https://github.com/open-coder-ai/chock-catalog) | Policies: The policies, each labelled by what it enforces, with replayed evals. |
| [context-report](https://github.com/open-coder-ai/context-report) | Evidence: A signed report of whether an agent artifact works. |
| [chock-threat-intel](https://github.com/open-coder-ai/chock-threat-intel) | Evidence: A weekly threat ledger, each entry scored against the catalog. |
| [chock-claude-plugins](https://github.com/open-coder-ai/chock-claude-plugins) | Plugins: The catalog as Claude Code plugins (generated). |
| [chock-copilot-plugins](https://github.com/open-coder-ai/chock-copilot-plugins) | Plugins: The catalog as Copilot CLI and VS Code plugins (generated). |
| [chock-cursor-plugins](https://github.com/open-coder-ai/chock-cursor-plugins) | Plugins: The catalog as Cursor plugins (generated). |
| [chock-codex-plugins](https://github.com/open-coder-ai/chock-codex-plugins) | Plugins: The catalog as Codex plugins (generated). |
| [chock-devin-plugins](https://github.com/open-coder-ai/chock-devin-plugins) | Plugins: The catalog as Devin plugins (generated). |
| [chock-quickstart](https://github.com/open-coder-ai/chock-quickstart) | Template: What chock init leaves behind. |
| [chock-example](https://github.com/open-coder-ai/chock-example) | Template: A working adoption, one policy per layer. |
| [.github](https://github.com/open-coder-ai/.github) | Community: Org profile and community health files. |

## Contributing

The most valuable contribution needs no code. Most rows in the matrix rest on vendor documentation rather
than on anyone watching the agent run. One command reports what your installed version does, and the
result becomes a `verified` record with your handle on it:

```bash
python3 tools/experiment.py run --agent <agent> --driver harness --report \
    --agent-version <version> --reporter @yourhandle > report.json
```

`--driver harness` makes it a witness: it runs your installed agent. Without it the driver falls back to
`reference`, which reports `basis: vendor-docs`: a contract test, not evidence of what your build does.
Paste the result into an [evidence report](https://github.com/open-coder-ai/agentseam/issues/new?template=evidence-report.yml);
a result that contradicts the matrix is the one we most want. The walk-through is in
[CONTRIBUTING.md](CONTRIBUTING.md#contributing-evidence-you-do-not-need-to-write-code).

| First contribution | Where to start |
|---|---|
| Turn a `vendor-docs` row into a live-run row | have the agent installed? [tools/VERIFY.md](tools/VERIFY.md), an hour, no code |
| Add an agent adapter | a vendor config entry, a matrix row and real-payload fixtures ([steps](CONTRIBUTING.md#adding-an-agent-adapter)); Goose, Crush and OpenCode are researched and unbuilt |
| Correct a matrix row that claims too much | the [matrix correction](https://github.com/open-coder-ai/agentseam/issues/new?template=matrix_correction.md) template |
| Write a guard others can adopt | ship it as a policy in [chock-catalog](https://github.com/open-coder-ai/chock-catalog) |
| Bugs and docs | a [good first issue](https://github.com/open-coder-ai/agentseam/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22) |

`pytest -q` and `ruff check .` are the whole local loop; the runtime path stays stdlib-only and every commit
is signed off (`git commit -s`). Adding an adapter must never require touching `contract.py`,
`dispatch.py` or any consumer; if it does, the abstraction is wrong. More: [Bundles](docs/bundles.md) ·
[Design](docs/design.md) · [per-vendor examples](docs/vendor-examples.md) · [ARCHITECTURE.md](ARCHITECTURE.md) ·
[SECURITY.md](SECURITY.md).

## License

Apache-2.0. See [LICENSE](LICENSE).

