"""Primitive 2: instruction files -- where each agent reads its standing instructions.

Every multi-agent repository ends up hand-maintaining a drawer of near-identical files:
CLAUDE.md, AGENTS.md, .cursor/rules/*, .github/copilot-instructions.md, GEMINI.md,
.windsurfrules, codex.md... They drift, and the drift is invisible until an agent
behaves differently from its neighbour.

This module owns the map and the writing. Two rules shape the design:

  * **Never clobber.** Instruction files hold human-authored content. We write a
    marker-delimited block and touch nothing outside it, so a rewrite updates our block
    and leaves the rest of the file exactly as it was.
  * **Prefer the shared file.** AGENTS.md is read natively by a large and growing set of
    agents. Writing one AGENTS.md and pointing the stragglers at it beats maintaining
    fifteen copies, so `plan()` says which agents are covered by the shared file and
    which genuinely need their own.
"""

from __future__ import annotations

import os

BEGIN = "<!-- agentseam:begin -->"
END = "<!-- agentseam:end -->"

#: The shared convention. Where an agent reads this natively, a pointer file is waste.
SHARED_FILE = "AGENTS.md"

#: agent -> instruction files it reads, most-preferred first.
#:
#: `shared` records whether the agent reads AGENTS.md natively. It is deliberately
#: conservative: False means "not established here", not "confirmed absent", and a
#: False costs only a small pointer file while a wrong True silently drops an agent's
#: instructions entirely.
INSTRUCTION_FILES = {
    "claude_code": {"files": ["CLAUDE.md", ".claude/CLAUDE.md"], "shared": False, "imports": "@AGENTS.md"},
    "codex_cli": {"files": ["AGENTS.md", "codex.md"], "shared": True, "imports": None},
    "cursor": {"files": [".cursor/rules/agentseam.mdc", ".cursorrules"], "shared": True, "imports": None},
    "vscode_copilot": {
        "files": [".github/copilot-instructions.md", ".github/agents/agentseam.agent.md"],
        "shared": True,
        "imports": None,
    },
    "gemini_cli": {"files": ["GEMINI.md", ".gemini/GEMINI.md"], "shared": True, "imports": None},
    "windsurf": {"files": [".windsurf/rules/agentseam.md", ".windsurfrules"], "shared": True, "imports": None},
    # Aider discovers nothing by convention: it reads the files listed under `read:` in
    # .aider.conf.yml and nothing else, which is why a sibling guardrail in this org ships
    # that conf file alongside its CONVENTIONS.md. `shared` was True here, claiming aider
    # picks up AGENTS.md natively -- the exact "wrong True" the comment above warns about,
    # which would have `discover()` write only AGENTS.md and report aider as covered while
    # aider read none of it. False is the conservative answer; the conf file itself is a
    # mechanism this module cannot yet express (`imports` renders a note, not a second file).
    "aider": {"files": ["CONVENTIONS.md"], "shared": False, "imports": None},
    "zed": {"files": [".rules"], "shared": True, "imports": None},
    "junie": {"files": [".junie/guidelines.md"], "shared": False, "imports": None},
    "devin": {"files": [".devin/README.md"], "shared": False, "imports": None},
    "grok": {"files": [".grok/GROK.md"], "shared": False, "imports": None},
    "kimi_code": {"files": [".kimi-code/AGENTS.md"], "shared": True, "imports": None},
    "replit": {"files": ["replit.md"], "shared": False, "imports": None},
    "tabnine": {"files": ["guidelines.md"], "shared": False, "imports": None},
    "antigravity": {"files": [".agents/rules/agentseam.md"], "shared": False, "imports": None},
}


def agents():
    return sorted(INSTRUCTION_FILES)


def paths(agent):
    """Files `agent` reads, most-preferred first. Unknown agent -> []."""
    row = INSTRUCTION_FILES.get(agent)
    return list(row["files"]) if row else []


def reads_shared(agent):
    row = INSTRUCTION_FILES.get(agent)
    return bool(row and row["shared"])


def discover(repo_root="."):
    """Which instruction files actually exist here, per agent.

    Answers "what is this repo already telling its agents, and where", which is the
    question anyone auditing a multi-agent repo starts with.
    """
    found = {}
    for agent in agents():
        present = [p for p in paths(agent) if os.path.exists(os.path.join(repo_root, p))]
        if present:
            found[agent] = present
    return found


def plan(targets=None, repo_root="."):
    """Decide the smallest set of writes that reaches every requested agent.

    Returns {"shared": path_or_None, "per_agent": {agent: path}, "covered": [agents]}.
    Agents that read AGENTS.md natively are listed under `covered` and get no file of
    their own -- writing them one would be a second copy to drift.
    """
    targets = sorted(targets) if targets else agents()
    unknown = [a for a in targets if a not in INSTRUCTION_FILES]
    if unknown:
        raise KeyError("unknown agent(s): %s" % ", ".join(unknown))

    covered = [a for a in targets if reads_shared(a)]
    needs_own = [a for a in targets if not reads_shared(a)]
    return {
        "shared": SHARED_FILE if covered else None,
        "covered": covered,
        "per_agent": {a: paths(a)[0] for a in needs_own},
    }


def _managed_block(text, agent=None):
    body = text.rstrip()
    note = ""
    if agent and INSTRUCTION_FILES.get(agent, {}).get("imports"):
        note = "\n\n(Shared instructions live in %s.)" % SHARED_FILE
    return "%s\n%s%s\n%s" % (BEGIN, body, note, END)


def render(existing, text, agent=None):
    """Return `existing` with our managed block inserted or replaced.

    Content outside the markers is preserved byte for byte -- this is the whole
    contract, since these files are mostly human-written.
    """
    block = _managed_block(text, agent)
    if existing and BEGIN in existing and END in existing:
        head, rest = existing.split(BEGIN, 1)
        _, tail = rest.split(END, 1)
        return head + block + tail
    if not existing:
        return block + "\n"
    sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    return existing + sep + block + "\n"


def write(text, targets=None, repo_root=".", dry_run=False):
    """Write `text` as a managed block into the fewest files that reach `targets`.

    Returns {path: "created"|"updated"|"unchanged"}.
    """
    decided = plan(targets, repo_root)
    results = {}
    wanted = []
    if decided["shared"]:
        wanted.append((decided["shared"], None))
    wanted.extend((path, agent) for agent, path in sorted(decided["per_agent"].items()))

    for rel, agent in wanted:
        full = os.path.join(repo_root, rel)
        existing = ""
        if os.path.exists(full):
            with open(full, encoding="utf-8") as fh:
                existing = fh.read()
        updated = render(existing, text, agent)
        if updated == existing:
            results[rel] = "unchanged"
            continue
        results[rel] = "updated" if existing else "created"
        if dry_run:
            continue
        parent = os.path.dirname(full)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(full, "w", encoding="utf-8") as fh:
            fh.write(updated)
    return results


def remove(targets=None, repo_root="."):
    """Strip our managed block from each file, leaving everything else intact."""
    removed = {}
    seen = set()
    for agent in sorted(targets) if targets else agents():
        for rel in [SHARED_FILE] + paths(agent):
            if rel in seen:
                continue
            seen.add(rel)
            full = os.path.join(repo_root, rel)
            if not os.path.exists(full):
                continue
            with open(full, encoding="utf-8") as fh:
                existing = fh.read()
            if BEGIN not in existing or END not in existing:
                continue
            head, rest = existing.split(BEGIN, 1)
            _, tail = rest.split(END, 1)
            cleaned = (head.rstrip("\n") + "\n" + tail.lstrip("\n")).strip() + "\n"
            with open(full, "w", encoding="utf-8") as fh:
                fh.write("" if cleaned.strip() == "" else cleaned)
            removed[rel] = "cleaned"
    return removed
