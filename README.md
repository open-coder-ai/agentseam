# agentseam

**Write one handler. Run it on every coding agent.**

Every agent — Claude Code, Cursor, VS Code Copilot, Codex, Gemini CLI, Windsurf — invented
its own hook system: different event names, different payload shapes, different ways to say
"no", different config files. So every tool built on top gets written once per agent, or
targets one agent and stops there.

agentseam is the layer underneath: one normalized event, one decision type, and an explicit
map of what each agent can *actually* do.

```python
from agentseam import run, Decision

def handler(event):
    if event.event == "pre_tool" and "AKIA" in (event.content or ""):
        return Decision.deny("no AWS keys in memory files")
    return Decision.allow()

run(handler)
```

```bash
agentseam install all "python3 my_handler.py" --events pre_tool
```

That handler now runs on Claude Code, Cursor, and VS Code Copilot — each getting its native
protocol, each wired into its own config file.

## It tells you the truth about what it can enforce

Agents are not equally capable, and pretending otherwise is how a "policy" silently fails.
The capability matrix is data, not marketing:

```
$ agentseam matrix        # trimmed to five of fifteen columns
                     aider           claude_code     cursor          vscode_copilot  zed
prompt_submit        none            enforced        enforceable     detect          none
pre_tool             none            enforced        enforceable     enforced        none
post_tool            none            detect          detect          detect          none
```

- **enforced** — the agent blocks, and fails closed if your hook dies
- **best-effort** — it blocks, but fails *open* (Cursor's default: a crashed hook allows)
- **detect** — you see it after the fact; prevention is not available (Cursor file edits
  fire `afterFileEdit`, after the write already landed)
- **enforceable** — it blocks and *can* be told to fail closed, but doesn't by default
  (Cursor's `failClosed: true`). "best-effort" would understate a surface you can make
  airtight; "enforced" would claim a default that isn't there. agentseam's installer asks
  for fail-closed on every gate it writes
- **none** — no hook surface at all (Zed, Aider). Said out loud rather than papered over.

`unadapted` is a fourth, deliberately separate state: agentseam has no hook adapter for
that agent yet. It is a claim about *us*, not about the agent — those agents still receive
instruction files, they just cannot have their tool calls gated here. Collapsing the two
would either slander an agent that does expose hooks or overstate our own coverage.

A `Decision.rewrite(...)` on an agent that cannot rewrite degrades to `ask`, never to a
silent pass-through. `agentseam doctor` reports what is wired on this machine and flags
capability rows that have not been re-verified in 90 days.

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

## One set of instructions, every agent

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
human wrote in those files is preserved untouched — and `instructions --list` shows what
a repo is already telling its agents.

## One policy, four incompatible permission languages

Every agent has a settings file with an allow/deny model, and no two of them are the same
kind of object. Claude Code evaluates an ordered rule list. Gemini CLI keeps tool-name
allowlists. Codex runs a Starlark program over command prefixes. VS Code holds a map of
auto-approve patterns. They do **not** have the same expressive power.

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

That second block is the point. VS Code's auto-approve map takes `false` for a pattern,
which reads like a denylist and is not one — the command still runs once a human clicks
through. (The `github.copilot.chat.agent.terminal.denyList` key it replaced never blocked
either.) Rendering a "deny" there would hand you a guardrail that stops nothing, so
agentseam hands back the rule unrendered with the reason instead, and the command exits
non-zero. Put it in CI and you find out that your policy doesn't survive the trip to an
agent *before* you rely on it.

The same honesty applies to the gaps we have in ourselves. Every agent the matrix knows
appears here — either with a recorded model, or named with the reason there isn't one, and
a test enforces that the two sets add up to the matrix exactly. A silently absent agent
would read as "nothing to say here" when the truth is "nobody looked".

The reasons distinguish two things that are easy to blur: an agent whose permission system
*provably exists* but whose schema we haven't read (Antigravity, Devin, Grok, Kimi Code all
prove it through their own hook events) versus one where nothing is established at all. And
a missing hook surface is never recorded as a missing permission model — Aider and Zed
expose no hooks, which says nothing about what their config files can restrict.

## Bundles: mostly the same directory, twice

A Claude Code plugin and a Gemini CLI extension turn out to be nearly the same thing
underneath two different manifests:

| part | Claude Code plugin | Gemini CLI extension | |
|---|---|---|---|
| skill | `skills/<name>/SKILL.md` | `skills/<name>/SKILL.md` | identical |
| subagent | `agents/<name>.md` | `agents/<name>.md` | identical |
| hooks | `hooks/hooks.json` | `hooks/hooks.json` | identical |
| command | `commands/<name>.md` | `commands/<name>.toml` | same folder, different format |
| manifest | `.claude-plugin/plugin.json` | `gemini-extension.json` | different |

So one directory serves both, and the real work is the second manifest and writing the
commands twice. VS Code has no bundle format at all — parts are found by location, so
committing the file *is* the install — and it reads several of Claude Code's own folders
natively: `.claude/skills`, `.claude/agents`, `.claude/rules`, and hooks straight out of
`.claude/settings.json`.

```bash
agentseam packaging
```

...prints each layout, the templates shared by more than one agent, and which folders an
agent reads that belong to somebody else. That last line matters in both directions: a
repo shipping `.claude/skills` is already shipping skills to VS Code, intended or not.

`plan(agent, bundle)` renders a bundle into the exact files an agent expects, and — as
with permissions — hands back what the format cannot hold, with a reason specific to that
agent. Gemini can't take a `.mcp.json`, but not because it lacks MCP: it declares servers
in the manifest instead, and saying "no MCP support" would be as wrong as saying nothing.

## See it per vendor before you install anything

[`examples/generated/`](examples/generated/) has a page for every agent agentseam can hook,
each showing the **same situation** — an agent about to write a secret into a file it will
read back later — in that vendor's own dialect: the config `install` writes, the normalized
event a handler sees, and what `allow` / `deny` / `ask` / `rewrite` each turn into on the
way back, including the ones that get reduced because the agent cannot express them.

There is a section for **every hook each agent supports**, in lifecycle order. Every block
is generated by running the library, and CI fails if the pages drift from what it actually
produces — an example nobody regenerates is a claim nobody checks.

What the pages cannot do is verify the vendors. Each row records what its claims rest on —
`live-run`, `live-run-partial`, `vendor-source`, `vendor-docs`, `third-party-install`,
`inherited` — and most are vendor documentation, which is a claim about what a vendor *says*
rather than an observation of what their build does. Only Claude Code's row rests on a full
live run; Cursor's rests on a partial one, with the observed events listed on the row. Vendors change hook
surfaces without notice, so **verify against your own installation before relying on any of
it**, and open an issue if a page is wrong.

```bash
python3 examples/generate.py           # rewrite the pages
python3 examples/generate.py --check   # what CI runs
```

## Verify a claim against your own agent

Only Claude Code's row rests on a full live run (Cursor's is partial). If you have another
of these agents installed, an hour turns its row from "the vendor says so" into evidence:

```bash
python3 tools/capture.py detect
python3 tools/capture.py install --agent cursor
# ... use the agent for a minute ...
python3 tools/capture.py report
python3 tools/capture.py uninstall --agent cursor
```

The probe always allows, so it cannot interfere with real work, and payloads are reduced to
shape before anything touches disk — keys and types survive, values do not. See
[tools/VERIFY.md](tools/VERIFY.md).

## Install

```bash
pip install agentseam
```

## Supported agents

| Agent | Tier | Config |
|---|---|---|
| Claude Code | block + rewrite | `.claude/settings.json` |
| VS Code Copilot | block + rewrite | `.github/hooks/*.json` |
| Cursor | block + rewrite (all tools, fail-open by default) | `.cursor/hooks.json` |
| Gemini CLI | block + rewrite (fail-open) | `.gemini/settings.json` |
| OpenAI Codex CLI | block + rewrite (fail-open) | `.codex/hooks.json` |
| Windsurf | block via exit code only; **no file-write event** | `.windsurf/hooks.json` |
| Zed, Aider | no hook surface at all | — |
| Devin | block + rewrite (fail-open) | `.devin/hooks.v1.json` |
| Grok CLI | block on PreToolUse only (fail-open) | `.grok/hooks/*.json` |
| Antigravity | block, and can refuse to let the agent stop (fail-open) | `.agents/hooks.json` |
| Kimi Code CLI | block on 3 of its 20 events (fail-open) | `config.toml` |
| Junie CLI | block + ask + rewrite, all native (fail-open) | `~/.junie/config.json` |
| Tabnine CLI | block on 6 of its 11 events, incl. post-tool (fail-open) | `.tabnine/agent/settings.json` |
| Replit | no hook surface found in its docs — instruction files work | — |

Goose, Crush, OpenCode: adapters planned; the
capability research is done and each is a module plus a matrix row.

## Design

- **stdlib only.** No dependencies, ever, in the adapter path — adapters must stay
  copy-portable into other projects that vendor single files.
- **Adapters own all vendor knowledge.** Adding an agent is a module plus a matrix row;
  no consumer changes.
- **Ownership-marked wiring.** Install is idempotent and uninstall is surgical: your own
  hooks in the same config are never touched.
- **The matrix carries provenance.** Every row records the version and date it was
  verified, and how.

[ARCHITECTURE.md](ARCHITECTURE.md) explains why those choices, what they cost, and the bug
classes they exist to prevent.

Apache-2.0.
