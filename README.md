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
$ agentseam matrix
                     aider           claude_code     cursor          vscode_copilot  zed
prompt_submit        none            enforced        detect          detect          none
pre_tool             none            enforced        best-effort     enforced        none
post_tool            none            detect          detect          detect          none
```

- **enforced** — the agent blocks, and fails closed if your hook dies
- **best-effort** — it blocks, but fails *open* (Cursor's default: a crashed hook allows)
- **detect** — you see it after the fact; prevention is not available (Cursor file edits
  fire `afterFileEdit`, after the write already landed)
- **none** — no hook surface at all (Zed, Aider). Said out loud rather than papered over.

A `Decision.rewrite(...)` on an agent that cannot rewrite degrades to `ask`, never to a
silent pass-through. `agentseam doctor` reports what is wired on this machine and flags
capability rows that have not been re-verified in 90 days.

## What it is for

Not just guardrails. Anything that wants to watch or shape an agent's life:

| | |
|---|---|
| **Observability** | one JSONL/OTel stream across every agent in the repo (`examples/event_log.py`) |
| **Notifications** | desktop/Slack ping on stop or prompt (`examples/notify.py`) |
| **Cost tracking** | token/cost meters that work regardless of which agent ran |
| **Guardrails** | secrets, memory governance, destructive-command blocks |
| **Process gates** | TDD enforcement, "tests before push" |
| **Context injection** | inject memory/instructions at session start |

## Install

```bash
pip install agentseam
```

## Supported agents

| Agent | Tier | Config |
|---|---|---|
| Claude Code | block + rewrite | `.claude/settings.json` |
| VS Code Copilot | block + rewrite | `.github/hooks/*.json` |
| Cursor | block (shell/MCP), detect (file edits) | `.cursor/hooks.json` |
| Gemini CLI | block + rewrite (fail-open) | `.gemini/settings.json` |
| OpenAI Codex CLI | block + rewrite (fail-open) | `.codex/hooks.json` |
| Zed, Aider | no hook surface | — |

Windsurf, Goose, Junie, Crush, OpenCode: adapters planned; the
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

Apache-2.0.
