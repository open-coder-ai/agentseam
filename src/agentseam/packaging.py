"""Primitive 3: packaging -- describe a bundle once, lay it out for every agent that has one.

A `Bundle` is a name, a version, and some parts: skills, subagents, commands. `plan()` turns
it into the exact files one agent expects, and -- as with permissions -- returns whatever
that agent has no way to hold.

The useful discovery is how much overlaps. `same_path_for()` reports the parts whose path is
*byte-identical* across the agents you name, which is the set you only have to write once.
For a skill, that is currently every agent with a recorded format: `skills/<name>/SKILL.md`
is the same file in a Claude Code plugin and a Gemini CLI extension, and VS Code will read
Claude Code's copy of it out of `.claude/skills` without being asked.
"""

from __future__ import annotations

import json

from .packaging_data import (
    ALSO_READS,
    COMMAND,
    HOOKS,
    MCP,
    PACKAGING,
    PART_LIMITS,
    PARTS,
    SHARED_SKILL_DIR,
    SKILL,
    SUBAGENT,
    UNRECORDED,
)

__all__ = [
    "Part",
    "Bundle",
    "Plan",
    "Unrepresentable",
    "agents",
    "layout",
    "supports",
    "same_path_for",
    "also_reads",
    "plan",
    "PARTS",
    "SKILL",
    "SUBAGENT",
    "COMMAND",
    "HOOKS",
    "MCP",
    "SHARED_SKILL_DIR",
    "UNRECORDED",
]


class Part:
    """One piece of a bundle: a kind, a name, and its body text."""

    __slots__ = ("kind", "name", "body", "description")

    def __init__(self, kind, name, body, description=None):
        if kind not in PARTS:
            raise ValueError("unknown part: %r" % (kind,))
        self.kind = kind
        self.name = name
        self.body = body
        self.description = description

    def __repr__(self):
        return "Part(%r, %r)" % (self.kind, self.name)


class Bundle:
    """A named, versioned set of parts."""

    __slots__ = ("name", "version", "description", "parts")

    def __init__(self, name, version="0.1.0", description=None, parts=()):
        self.name = name
        self.version = version
        self.description = description
        self.parts = list(parts)

    def of_kind(self, kind):
        return [p for p in self.parts if p.kind == kind]

    def __repr__(self):
        return "Bundle(%r, %d parts)" % (self.name, len(self.parts))


class Unrepresentable:
    """A part this agent's format has nowhere to put, and why."""

    __slots__ = ("part", "reason")

    def __init__(self, part, reason):
        self.part = part
        self.reason = reason

    def __repr__(self):
        return "Unrepresentable(%r, %r)" % (self.part, self.reason)


class Plan:
    """The files to write, relative to the bundle root, plus what did not fit."""

    __slots__ = ("agent", "root", "files", "unrepresentable")

    def __init__(self, agent, root, files, unrepresentable=()):
        self.agent = agent
        self.root = root
        self.files = files
        self.unrepresentable = list(unrepresentable)

    @property
    def complete(self):
        return not self.unrepresentable

    def __repr__(self):
        return "Plan(%s, %d files, dropped=%d)" % (self.agent, len(self.files), len(self.unrepresentable))


# --- queries --------------------------------------------------------------------


def agents():
    """Agents with a recorded packaging format."""
    return sorted(PACKAGING)


def layout(agent):
    """The recorded format for `agent`, or None."""
    row = PACKAGING.get(agent)
    return dict(row) if row else None


def supports(agent, part):
    """The path template for `part`, or None where the agent has no equivalent."""
    row = PACKAGING.get(agent)
    return row["parts"].get(part) if row else None


def same_path_for(part, targets=None):
    """Agents among `targets` whose path template for `part` is identical, grouped by template.

    The single-entry groups are the interesting ones in reverse: they are the parts you have
    to write more than once.
    """
    grouped = {}
    for agent in targets or agents():
        template = supports(agent, part)
        if template:
            grouped.setdefault(template, []).append(agent)
    return {template: sorted(names) for template, names in grouped.items()}


def also_reads(agent, part=None):
    """Folders `agent` reads that belong to another agent's layout.

    Committing a part to one of these ships it to `agent` too, whether or not that was the
    intent -- worth knowing in both directions.
    """
    rows = ALSO_READS.get(agent, {})
    if part is None:
        return {k: list(v) for k, v in rows.items()}
    return list(rows.get(part, ()))


# --- rendering ------------------------------------------------------------------


def _toml_string(text):
    """A TOML basic string. Multi-line bodies use the triple-quoted form."""
    escaped = text.replace("\\", "\\\\").replace('"""', '\\"\\"\\"')
    return '"""\n%s\n"""' % escaped if "\n" in text else '"%s"' % escaped.replace('"', '\\"')


def _render_command(agent, part):
    if agent == "gemini_cli":
        lines = []
        if part.description:
            lines.append("description = %s" % _toml_string(part.description))
        lines.append("prompt = %s" % _toml_string(part.body))
        return "\n".join(lines) + "\n"
    return part.body


def _manifest(agent, bundle, kinds):
    """The bundle manifest, including any component paths this host declares rather than finds.

    Two shapes hide behind one word. Claude Code and Gemini CLI find components by LOCATION:
    `skills/<name>/SKILL.md` is loaded because of where it sits, and the manifest carries only
    identity. Codex and Cursor RESOLVE components from the manifest -- Codex validates the
    `./...` syntax of each declared path -- so a manifest carrying only name and version ships
    a plugin whose skills and hooks are never loaded, and nothing reports an error.

    Only the parts the bundle actually has are declared. Pointing at `./skills` in a bundle
    with no skills advertises a directory that is not there.
    """
    row = PACKAGING[agent]
    if not row["manifest"]:
        return None
    body = {"name": bundle.name, "version": bundle.version}
    if bundle.description:
        body["description"] = bundle.description
    for kind, (key, value) in sorted((row.get("declares") or {}).items()):
        if kind in kinds:
            body[key] = value
    return json.dumps(body, indent=2, sort_keys=True) + "\n"


def plan(agent, bundle):
    """Lay `bundle` out for `agent`, reporting every part the format cannot hold.

    Raises KeyError for an agent with no recorded format, including the ones in UNRECORDED --
    an empty file list would read as "nothing to do" rather than "we do not know".
    """
    if agent not in PACKAGING:
        raise KeyError("%s: %s" % (agent, UNRECORDED.get(agent, "no packaging format recorded")))
    row = PACKAGING[agent]
    files = {}
    dropped = []

    holdable = {p.kind for p in bundle.parts if row["parts"].get(p.kind)}
    manifest = _manifest(agent, bundle, holdable)
    if manifest:
        files[row["manifest"]] = manifest

    for part in bundle.parts:
        template = row["parts"].get(part.kind)
        if not template:
            reason = PART_LIMITS.get((agent, part.kind), "this format has no place for a %s" % part.kind)
            dropped.append(Unrepresentable(part, reason))
            continue
        body = _render_command(agent, part) if part.kind == COMMAND else part.body
        files[template.format(name=part.name)] = body

    root = row["project_root"].format(bundle=bundle.name)
    return Plan(agent, root, files, dropped)
