"""Primitive 2: instruction files -- where each agent reads its standing instructions."""

from __future__ import annotations

import os
import re

BEGIN = "<!-- agentseam:begin -->"
END = "<!-- agentseam:end -->"

_BEGIN_LINE = re.compile("^" + re.escape(BEGIN), re.MULTILINE)
_END_LINE = re.compile("^" + re.escape(END), re.MULTILINE)

_REVERSED = "the end marker comes before the begin marker; fix the file by hand"

SHARED_FILE = "AGENTS.md"

INSTRUCTION_FILES = {
    "claude_code": {"files": ["CLAUDE.md", ".claude/CLAUDE.md"], "shared": False, "imports": "@AGENTS.md"},
    "codex_cli": {"files": ["AGENTS.md", "codex.md"], "shared": True, "imports": None},
    "cursor": {"files": [".cursor/rules/agentseam.mdc", ".cursorrules"], "shared": True, "imports": None},
    "vscode_copilot": {
        "files": [".github/copilot-instructions.md", ".github/agents/agentseam.agent.md"],
        "shared": True,
        "imports": None,
    },
    "copilot": {
        "files": [".github/copilot-instructions.md", ".github/agents/agentseam.agent.md"],
        "shared": True,
        "imports": None,
    },
    "gemini_cli": {"files": ["GEMINI.md", ".gemini/GEMINI.md"], "shared": True, "imports": None},
    "windsurf": {"files": [".windsurf/rules/agentseam.md", ".windsurfrules"], "shared": True, "imports": None},
    "aider": {"files": ["CONVENTIONS.md"], "shared": False, "imports": None},
    "zed": {"files": [".rules"], "shared": True, "imports": None},
    "junie": {"files": [".junie/guidelines.md"], "shared": False, "imports": None},
    "devin": {"files": [".devin/README.md"], "shared": False, "imports": None},
    "grok": {"files": ["AGENTS.md"], "shared": True, "imports": None},
    "kimi_code": {"files": [".kimi-code/AGENTS.md"], "shared": True, "imports": None},
    "opencode": {"files": ["AGENTS.md"], "shared": True, "imports": None},
    "kilo_code": {"files": ["AGENTS.md"], "shared": True, "imports": None},
    "cline": {"files": ["AGENTS.md"], "shared": True, "imports": None},
    "roo_code": {"files": ["AGENTS.md"], "shared": True, "imports": None},
    "goose": {"files": ["AGENTS.md"], "shared": True, "imports": None},
    "openhands": {"files": ["AGENTS.md"], "shared": True, "imports": None},
    "amp": {"files": ["AGENTS.md"], "shared": True, "imports": None},
    "kiro": {"files": ["AGENTS.md"], "shared": True, "imports": None},
    "factory_droid": {"files": ["AGENTS.md"], "shared": True, "imports": None},
    "mistral_vibe": {"files": ["AGENTS.md"], "shared": True, "imports": None},
    "deepseek_harness": {"files": ["AGENTS.md"], "shared": True, "imports": None},
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
    """Which instruction files actually exist here, per agent."""
    found = {}
    for agent in agents():
        present = [p for p in paths(agent) if os.path.exists(os.path.join(repo_root, p))]
        if present:
            found[agent] = present
    return found


def plan(targets=None, repo_root="."):  # noqa: ARG001 (repo_root mirrors discover(repo_root)'s
    # signature -- cli.py and callers pass args.repo to both uniformly -- though this plan is
    # path-agnostic; it decides *which* files, write()/discover() decide *where*)
    """Decide the smallest set of writes that reaches every requested agent."""
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


def _split(existing):
    """(head, tail) around our block, or None when there is none; markers count only at a line start."""
    begin = _BEGIN_LINE.search(existing)
    end = _END_LINE.search(existing, begin.end()) if begin else None
    if begin and end:
        return existing[: begin.start()], existing[end.end() :]
    if begin and _END_LINE.search(existing):
        raise ValueError(_REVERSED)
    return None


def render(existing, text, agent=None):
    """Return `existing` with our managed block inserted or replaced."""
    block = _managed_block(text, agent)
    parts = _split(existing) if existing else None
    if parts:
        return parts[0] + block + parts[1]
    if not existing:
        return block + "\n"
    sep = "" if existing.endswith("\n\n") else ("\n" if existing.endswith("\n") else "\n\n")
    return existing + sep + block + "\n"


def write(text, targets=None, repo_root=".", *, dry_run=False):
    """Write `text` as a managed block into the fewest files that reach `targets`."""
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
        try:
            updated = render(existing, text, agent)
        except ValueError as exc:
            raise ValueError("%s: %s" % (rel, exc)) from exc
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
        for rel in [SHARED_FILE, *paths(agent)]:
            if rel in seen:
                continue
            seen.add(rel)
            full = os.path.join(repo_root, rel)
            if not os.path.exists(full):
                continue
            with open(full, encoding="utf-8") as fh:
                existing = fh.read()
            try:
                parts = _split(existing)
            except ValueError as exc:
                raise ValueError("%s: %s" % (rel, exc)) from exc
            if not parts:
                continue
            head, tail = parts
            cleaned = (head.rstrip("\n") + "\n" + tail.lstrip("\n")).strip() + "\n"
            with open(full, "w", encoding="utf-8") as fh:
                fh.write("" if cleaned.strip() == "" else cleaned)
            removed[rel] = "cleaned"
    return removed
