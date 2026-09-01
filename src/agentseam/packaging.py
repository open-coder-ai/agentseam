"""Primitive 3: packaging -- describe a bundle once, lay it out for every agent that has one."""

from __future__ import annotations

import json

from .packaging_data import (
    ALSO_READS,
    COMMAND,
    EXECUTABLE,
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
    "plugin_root",
    "executable_ref",
    "PARTS",
    "SKILL",
    "SUBAGENT",
    "COMMAND",
    "HOOKS",
    "MCP",
    "EXECUTABLE",
    "SHARED_SKILL_DIR",
    "UNRECORDED",
]


class Part:
    """One piece of a bundle: a kind, a name, and its body text."""

    __slots__ = ("kind", "name", "body", "description", "executable")

    def __init__(self, kind, name, body, description=None, executable=False):
        if kind not in PARTS:
            raise ValueError("unknown part: %r" % (kind,))
        self.kind = kind
        self.name = name
        self.body = body
        self.description = description
        self.executable = executable

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

    __slots__ = ("agent", "root", "files", "unrepresentable", "executables")

    def __init__(self, agent, root, files, unrepresentable=(), executables=frozenset()):
        self.agent = agent
        self.root = root
        self.files = files
        self.unrepresentable = list(unrepresentable)
        self.executables = frozenset(executables)

    @property
    def complete(self):
        return not self.unrepresentable

    def __repr__(self):
        return "Plan(%s, %d files, dropped=%d)" % (self.agent, len(self.files), len(self.unrepresentable))


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
    """Agents among `targets` whose path template for `part` is identical, grouped by template."""
    grouped = {}
    for agent in targets or agents():
        template = supports(agent, part)
        if template:
            grouped.setdefault(template, []).append(agent)
    return {template: sorted(names) for template, names in grouped.items()}


def also_reads(agent, part=None):
    """Folders `agent` reads that belong to another agent's layout."""
    rows = ALSO_READS.get(agent, {})
    if part is None:
        return {k: list(v) for k, v in rows.items()}
    return list(rows.get(part, ()))


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
    """The bundle manifest, including any component paths this host declares rather than finds."""
    row = PACKAGING[agent]
    if not row["manifest"]:
        return None
    body = {"name": bundle.name, "version": bundle.version}
    if bundle.description:
        body["description"] = bundle.description
    for key, value in (row.get("manifest_fixed") or {}).items():
        body[key] = value
    for kind, (key, value) in sorted((row.get("declares") or {}).items()):
        if kind in kinds:
            body[key] = value
    return json.dumps(body, indent=2, sort_keys=True) + "\n"


def plan(agent, bundle):
    """Lay `bundle` out for `agent`, reporting every part the format cannot hold."""
    if agent not in PACKAGING:
        raise KeyError("%s: %s" % (agent, UNRECORDED.get(agent, "no packaging format recorded")))
    row = PACKAGING[agent]
    files = {}
    dropped = []
    executables = set()

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
        path = template.format(name=part.name)
        files[path] = body
        if part.kind == EXECUTABLE and part.executable:
            executables.add(path)

    root = row["project_root"].format(bundle=bundle.name)
    return Plan(agent, root, files, dropped, executables)


def plugin_root(agent):
    """The token a hook command should use to reach its own plugin directory."""
    row = PACKAGING.get(agent)
    tokens = row.get("plugin_root") if row else None
    return tokens[0] if tokens else None


def executable_ref(agent, path):
    """The string a HOOKS command should use to reach a rendered EXECUTABLE at `path`."""
    row = PACKAGING.get(agent)
    if not row:
        return None
    if row["unit"] is None:
        return path
    token = plugin_root(agent)
    return "%s/%s" % (token, path) if token else None
