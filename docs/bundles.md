# Bundles: mostly the same directory, twice

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
