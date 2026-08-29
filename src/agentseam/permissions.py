"""Primitive 4: config and permissions -- one policy, spelled in each agent's own dialect.

A rule here names a *capability* ("shell", "file_write") rather than a tool, because
`Bash`, `run_shell_command` and the terminal tool are three vendors' spellings of one
idea. `plan()` renders a rule set into an agent's native config and, just as importantly,
hands back everything that could **not** be rendered and why.

That second return value is the whole design. Every vendor's permission config is a
different kind of object -- Claude Code evaluates an ordered rule list, Gemini CLI keeps
tool-name allowlists, Codex runs a Starlark program over command prefixes, VS Code holds a
map of auto-approve patterns -- and they do not have the same expressive power. A renderer
that quietly emitted the nearest-looking key would produce config that reads like the
policy and does not enforce it. So a rule with no faithful expression is returned unrendered
with the reason, and the caller decides what to do about the gap.
"""

from __future__ import annotations

import os

from .permissions_data import ACTIONS, CAPABILITIES, CAPABILITY, CONFIG_FILES, UNRECORDED
from .permissions_render import RENDERERS, Unrepresentable, render_content_rules

__all__ = [
    "Rule",
    "ContentRule",
    "Plan",
    "Unrepresentable",
    "agents",
    "config_files",
    "capability",
    "expresses",
    "deny_is_authoritative",
    "plan",
    "discover",
    "UNRECORDED",
]


class Rule:
    """One policy statement: do `action` to `capability`, optionally narrowed by `specifier`.

    The specifier is vendor-shaped by necessity (a command prefix, a path glob) -- there is
    no cross-vendor grammar for "which invocations", and inventing one would only move the
    lossiness somewhere less visible.
    """

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


class ContentRule:
    """A deny on CONTENT matching a regex -- what bytes a file or a piece of text contain,
    never which tool touched them.

    `Rule` narrows an invocation (a command prefix, a path glob): it is still a statement
    about a tool call. This is a different kind of statement with no shared vocabulary --
    the same secret trips it whether it arrives via `Read`, `Grep`, an MCP tool, or a tool
    this project has never heard of, and a `capability`/`specifier` pair has nowhere to put
    that. `kind` distinguishes matching a file's contents (`FILE`) from matching a bare
    string a handler already has in hand (`TEXT`, e.g. a prompt or a tool's stdout).

    `pattern` is a regular expression, spelled once and rendered into whichever agent's
    config can hold it. Keep it lookahead/lookbehind-free: `(?=`, `(?!`, `(?<=`, `(?<!` are
    not guaranteed to survive translation to every vendor's own regex engine, several of
    which are RE2-family and reject them outright -- a pattern that only ever runs through
    Python's `re` here can still be shipped into a config file read by a different engine
    entirely. This module does not enforce that today (no renderer accepts a `ContentRule`
    yet -- see `permissions_render.render_content_rules`), but a pattern written for real
    cross-vendor use should hold to it from the start rather than needing a rewrite later.
    """

    __slots__ = ("kind", "pattern", "message")

    FILE = "file"
    TEXT = "text"
    KINDS = (FILE, TEXT)

    def __init__(self, kind, pattern, message=None):
        if kind not in self.KINDS:
            raise ValueError("unknown content-rule kind: %r (expected one of %s)" % (kind, self.KINDS))
        if not pattern:
            raise ValueError("a content rule needs a pattern; an empty one matches everything or nothing by accident")
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

    __slots__ = ("agent", "fragment", "path", "format", "unrepresentable")

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


# --- queries --------------------------------------------------------------------


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
    """Render `rules` into `agent`'s native config, reporting whatever could not be rendered.

    `rules` may mix `Rule` (a tool invocation) and `ContentRule` (a content match) --
    each kind is rendered by its own path and the results merged, so a caller does not have
    to split one policy into two calls. Raises KeyError for an agent with no recorded
    permission model -- including the ones in UNRECORDED, where the honest answer is "we do
    not know", not an empty config.
    """
    if agent not in RENDERERS:
        reason = UNRECORDED.get(agent, "no permission model recorded for this agent")
        raise KeyError("%s: %s" % (agent, reason))
    tool_rules = [r for r in rules if isinstance(r, Rule)]
    content_rules = [r for r in rules if isinstance(r, ContentRule)]
    fragment, dropped = RENDERERS[agent](tool_rules)
    content_fragment, content_dropped = render_content_rules(agent, content_rules)
    dropped = dropped + content_dropped
    if content_fragment:
        # Not exercised today -- every agent recorded here refuses every ContentRule (see
        # render_content_rules) -- but a caller merging a future non-empty content fragment
        # into a non-dict one (codex_cli's Starlark text) needs a loud failure, not a
        # silently wrong config.
        if not isinstance(fragment, dict) or not isinstance(content_fragment, dict):
            raise TypeError("%s: cannot merge a non-dict permission fragment with rendered content rules" % agent)
        fragment = dict(fragment, **content_fragment)
    return Plan(agent, fragment, *_target(agent), unrepresentable=dropped)


def _target(agent):
    """Where a rendered policy should be written: the project file, not the strongest one.

    Claude Code's highest-precedence file is managed-settings.json, which an administrator
    deploys to a fleet. Naming it here because it outranks the others would point a project
    policy at a machine-wide one, so the project-scoped file wins and precedence is left to
    `config_files()` to report.
    """
    rows = config_files(agent)
    for row in rows:
        if row["scope"] == "project":
            return row["path"], row["format"]
    return rows[0]["path"], rows[0]["format"]


# --- discovery ------------------------------------------------------------------


def discover(repo_root="."):
    """Which permission config files actually exist here, per agent.

    Project-scoped paths are resolved under `repo_root`; user- and managed-scoped paths are
    reported but not probed, since where they live is the host's business and a miss there
    would say more about this process's HOME than about the machine.
    """
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
