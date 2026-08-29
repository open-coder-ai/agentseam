"""Per-agent renderers: one policy, four genuinely different config languages.

Split out of `permissions` because rendering is a different activity from querying the
model, and because each of these functions is where a specific vendor's expressive limit
gets named. A renderer returns `(fragment, dropped)`; the dropped list is not an error
path, it is the honest half of the answer.
"""

from __future__ import annotations

import json

from .permissions_data import ALLOW, ASK, CAPABILITY, DENY


class Unrepresentable:
    """A rule this agent's config has no faithful way to state, and the reason."""

    __slots__ = ("rule", "reason")

    def __init__(self, rule, reason):
        self.rule = rule
        self.reason = reason

    def __repr__(self):
        return "Unrepresentable(%r, %r)" % (self.rule, self.reason)


def _tools_for(agent, rule):
    """Vendor tool names for a rule's capability, or () when the agent has none."""
    return CAPABILITY[agent]["tools"].get(rule.capability, ())


def _spell(tool, specifier):
    return "%s(%s)" % (tool, specifier) if specifier else tool


def _render_claude_code(rules):
    buckets = {ALLOW: [], ASK: [], DENY: []}
    dropped = []
    for rule in rules:
        tools = _tools_for("claude_code", rule)
        if not tools:
            dropped.append(Unrepresentable(rule, "no tool covers %s here" % rule.capability))
            continue
        for tool in tools:
            buckets[rule.action].append(_spell(tool, rule.specifier))
    fragment = {"permissions": {a: buckets[a] for a in (ALLOW, ASK, DENY) if buckets[a]}}
    return fragment, dropped


def _render_gemini_cli(rules):
    fragment = {}
    dropped = []
    for rule in rules:
        tools = _tools_for("gemini_cli", rule)
        if not tools:
            dropped.append(Unrepresentable(rule, "no tool covers %s here" % rule.capability))
            continue
        if rule.action == DENY and rule.specifier:
            dropped.append(
                Unrepresentable(
                    rule,
                    "tools.exclude removes a whole tool from discovery; it cannot exclude "
                    "only the invocations matching %r" % (rule.specifier,),
                )
            )
            continue
        key = CAPABILITY["gemini_cli"]["actions"][rule.action]
        section, leaf = key.split(".", 1)
        entries = fragment.setdefault(section, {}).setdefault(leaf, [])
        for tool in tools:
            # exclude takes bare tool names; allowed/confirmationRequired take specifiers.
            entries.append(tool if rule.action == DENY else _spell(tool, rule.specifier))
    return fragment, dropped


_CODEX_DECISION = {ALLOW: "allow", ASK: "prompt", DENY: "forbidden"}


def _render_codex_cli(rules):
    lines = []
    dropped = []
    for rule in rules:
        if not _tools_for("codex_cli", rule):
            dropped.append(
                Unrepresentable(
                    rule,
                    "execpolicy matches command token prefixes, so it has no way to state a "
                    "rule about %s" % rule.capability,
                )
            )
            continue
        if not rule.specifier:
            dropped.append(
                Unrepresentable(rule, "a prefix rule needs a command prefix; a bare shell rule matches nothing")
            )
            continue
        pattern = ", ".join(json.dumps(token) for token in rule.specifier.split())
        lines.append(
            'prefix_rule(\n    pattern = [%s],\n    decision = "%s",\n)' % (pattern, _CODEX_DECISION[rule.action])
        )
    return "\n\n".join(lines), dropped


def _render_vscode_copilot(rules):
    approve = {}
    dropped = []
    for rule in rules:
        if not _tools_for("vscode_copilot", rule):
            dropped.append(
                Unrepresentable(
                    rule,
                    "the auto-approve map covers terminal commands only, so it cannot state a "
                    "rule about %s" % rule.capability,
                )
            )
            continue
        if rule.action == DENY:
            dropped.append(
                Unrepresentable(
                    rule,
                    "this map has no deny: setting a pattern false withholds auto-approval but "
                    "still lets a human approve the command, so it would not block",
                )
            )
            continue
        if not rule.specifier:
            dropped.append(Unrepresentable(rule, "an auto-approve entry needs a command pattern to match"))
            continue
        approve[rule.specifier] = rule.action == ALLOW
    fragment = {"chat.tools.terminal.autoApprove": approve} if approve else {}
    return fragment, dropped


RENDERERS = {
    "claude_code": _render_claude_code,
    "gemini_cli": _render_gemini_cli,
    "codex_cli": _render_codex_cli,
    "vscode_copilot": _render_vscode_copilot,
}

# --- content-pattern rules (ContentRule): the honesty gate ----------------------
#
# Verified 2026-08-29, read directly against each vendor: none of the four permission
# surfaces this module knows about matches CONTENT. Each one matches a tool name, a command
# prefix, or a path glob -- the same axis `Rule.specifier` already covers, not a new one.
# Claude Code's managed settings were the one candidate a consumer might reasonably expect
# this from (its rule syntax is the richest of the four); a native regex/content-pattern
# permission rule was requested there and closed **"not planned"** upstream
# (anthropics/claude-code#37509). The real, existing mechanism for content-based denial on
# every agent here is a consumer-authored hook that inspects the payload itself and returns
# its own decision -- a different primitive (agentseam.install/dispatch), not a permissions
# rule. Rendering a ContentRule into any of these four configs -- even the one that looks
# closest -- would produce a fragment that reads like a content policy and enforces nothing,
# which is exactly the failure `permissions.plan()` exists to make visible instead of hiding.
_CONTENT_REASON = {
    "claude_code": (
        "permissions.{allow,ask,deny} match a tool name, optionally narrowed by a "
        "command-prefix/path-glob specifier -- none of the three reads file or text "
        "content. A native content-pattern permission rule was requested and closed "
        "'not planned' upstream (anthropics/claude-code#37509, read 2026-08-29); the real "
        "mechanism is a consumer-authored hook (see agentseam.install/dispatch) that "
        "inspects the payload and returns its own decision, which is a different "
        "primitive from a permissions rule."
    ),
    "gemini_cli": (
        "tools.allowed/tools.exclude/tools.confirmationRequired match by tool name; none "
        "inspects the argument bytes, so there is no way to gate on content a tool reads "
        "or writes."
    ),
    "codex_cli": (
        "execpolicy's prefix_rule matches ordered command tokens; the sandbox+execpolicy "
        "model has no content-scanning primitive at all, for shell commands or anything "
        "else."
    ),
    "vscode_copilot": (
        "the auto-approve map matches terminal command patterns and has no deny at all "
        "(see the tool-rule DENY case above); there is no content-scanning primitive here "
        "either."
    ),
}


def render_content_rules(agent, rules):
    """Every `ContentRule`, for every agent recorded here today: reported, never rendered.

    See the module note above for why. Returns `(fragment, dropped)` like the tool-rule
    renderers, so `permissions.plan()` can merge the two uniformly; `fragment` is always
    `{}` until a vendor's real content-scanning surface is verified and this table grows a
    real renderer for it.
    """
    if not rules:
        return {}, []
    reason = _CONTENT_REASON.get(agent, "no content-pattern rule kind is recorded as expressible for this agent")
    return {}, [Unrepresentable(rule, reason) for rule in rules]
