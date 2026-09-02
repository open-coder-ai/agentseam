"""Primitive 4: config and permissions -- one policy, spelled in each agent's own dialect."""

from __future__ import annotations

import os

from .permissions_data import ACTIONS, CAPABILITIES, CAPABILITY, CONFIG_FILES, UNRECORDED
from .permissions_render import RENDERERS, Unrepresentable, render_content_rules

__all__ = [
    "UNRECORDED",
    "ContentRule",
    "Plan",
    "Rule",
    "Unrepresentable",
    "agents",
    "capability",
    "config_files",
    "deny_is_authoritative",
    "discover",
    "expresses",
    "plan",
]


class Rule:
    """One policy statement: do `action` to `capability`, optionally narrowed by `specifier`."""

    __slots__ = ("action", "capability", "specifier")

    def __init__(self, action, capability, specifier=None):
        if action not in ACTIONS:
            raise ValueError("unknown action: %r" % (action,))
        if capability not in CAPABILITIES:
            raise ValueError("unknown capability: %r" % (capability,))
        self.action = action
        self.capability = capability
        self.specifier = specifier

    def __eq__(self, other):
        return isinstance(other, Rule) and (
            (self.action, self.capability, self.specifier) == (other.action, other.capability, other.specifier)
        )

    def __hash__(self):
        return hash((self.action, self.capability, self.specifier))

    def __repr__(self):
        return "Rule(%r, %r, %r)" % (self.action, self.capability, self.specifier)


_EMPTY_PATTERN = "a content rule needs a pattern; an empty one matches everything or nothing by accident"


class ContentRule:
    """A deny on CONTENT matching a regex -- what bytes a file or a piece of text contain,"""

    __slots__ = ("kind", "message", "pattern")

    FILE = "file"
    TEXT = "text"
    KINDS = (FILE, TEXT)

    def __init__(self, kind, pattern, message=None):
        if kind not in self.KINDS:
            raise ValueError("unknown content-rule kind: %r (expected one of %s)" % (kind, self.KINDS))
        if not pattern:
            raise ValueError(_EMPTY_PATTERN)
        self.kind = kind
        self.pattern = pattern
        self.message = message

    def __eq__(self, other):
        return isinstance(other, ContentRule) and (
            (self.kind, self.pattern, self.message) == (other.kind, other.pattern, other.message)
        )

    def __hash__(self):
        return hash((self.kind, self.pattern, self.message))

    def __repr__(self):
        return "ContentRule(%r, %r)" % (self.kind, self.pattern)


class Plan:
    """What `plan()` produced: a native fragment, plus what did not survive."""

    __slots__ = ("agent", "format", "fragment", "path", "unrepresentable")

    def __init__(self, agent, fragment, path, fmt, unrepresentable=()):
        self.agent = agent
        self.fragment = fragment
        self.path = path
        self.format = fmt
        self.unrepresentable = list(unrepresentable)

    @property
    def complete(self):
        """True when every rule was rendered. A caller enforcing policy should check this."""
        return not self.unrepresentable

    def __repr__(self):
        return "Plan(%s, complete=%s, dropped=%d)" % (self.agent, self.complete, len(self.unrepresentable))


def agents():
    """Agents with a recorded permission model."""
    return sorted(CAPABILITY)


def config_files(agent):
    """Config files for `agent`, highest precedence first. Unknown agent -> []."""
    return [dict(row) for row in CONFIG_FILES.get(agent, ())]


def capability(agent):
    """The full recorded model for `agent`, or None."""
    row = CAPABILITY.get(agent)
    return dict(row) if row else None


def expresses(agent, action):
    """The config key implementing `action` for `agent`, or None if it cannot say it."""
    row = CAPABILITY.get(agent)
    return row["actions"].get(action) if row else None


def deny_is_authoritative(agent):
    """Can a deny be overridden by an allow? True/False, or None where unestablished."""
    row = CAPABILITY.get(agent)
    return row["deny_authoritative"] if row else None


def plan(agent, rules):
    """Render `rules` into `agent`'s native config, reporting whatever could not be rendered."""
    if agent not in RENDERERS:
        reason = UNRECORDED.get(agent, "no permission model recorded for this agent")
        raise KeyError("%s: %s" % (agent, reason))
    tool_rules = [r for r in rules if isinstance(r, Rule)]
    content_rules = [r for r in rules if isinstance(r, ContentRule)]
    fragment, dropped = RENDERERS[agent](tool_rules)
    content_fragment, content_dropped = render_content_rules(agent, content_rules)
    dropped = dropped + content_dropped
    if content_fragment:
        if not isinstance(fragment, dict) or not isinstance(content_fragment, dict):
            raise TypeError("%s: cannot merge a non-dict permission fragment with rendered content rules" % agent)
        fragment = dict(fragment, **content_fragment)
    return Plan(agent, fragment, *_target(agent), unrepresentable=dropped)


def _target(agent):
    """Where a rendered policy should be written: the project file, not the strongest one."""
    rows = config_files(agent)
    for row in rows:
        if row["scope"] == "project":
            return row["path"], row["format"]
    return rows[0]["path"], rows[0]["format"]


def discover(repo_root="."):
    """Which permission config files actually exist here, per agent."""
    found = {}
    for agent in agents():
        present = []
        for row in config_files(agent):
            if row["scope"] in ("project", "local"):
                path = os.path.join(repo_root, row["path"])
                if os.path.exists(path):
                    present.append(dict(row, resolved=path))
        if present:
            found[agent] = present
    return found
