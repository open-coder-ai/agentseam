"""Executed against the D1 golden fixture: the `hook_config()` wrapper shape."""

from __future__ import annotations

from .gates import _load_fixture

_EXTRA = {
    # Event wiring, not an entry field: pre_mcp_tool_use is wired BESIDE pre_run_command
    # whenever pre_tool is (windsurf.py:106-107), so it must not be copied into entries.
    "windsurf": {"also_wires": {"pre_tool": "pre_mcp_tool_use"}},
    # FileChanged's matcher is the watch list itself: "each segment is registered as a literal
    # filename", and "Claude Code starts the watcher only when something names a file to watch"
    # (code.claude.com/docs/en/hooks, FileChanged, read 2026-10-13).
    "claude_code": {"watch_list_events": ["file_changed"]},
    # PermissionDenied fires "when the permission system denies a tool call" and parses as
    # tool_failure, so it is wired beside PostToolUseFailure (docs.x.ai/build/features/hooks, read
    # 2026-10-13). StopFailure ("ends with an API error") is an API failure, not the turn end a
    # stop handler is installed for, and PostCompact parses as unknown, so neither is wired.
    "grok": {"also_wires": {"tool_failure": "PermissionDenied"}},
    "codex_cli": {"entry_extra": {"commandWindows": "powershell wrapper (_windows.py)"}},
    "tabnine": {"entry_extra": {"name": "agentseam"}},
    # goose reads on_failure at PreToolUse only and ignores it elsewhere; "block" makes a
    # failed hook deny instead of being skipped (goose-docs.ai hooks guide, read 2026-10-11).
    "goose": {"entry_extra": {"on_failure": "block"}},
    # Vibe reads [[hooks]] {name, type, match, command}: same rule, its own key names.
    "mistral_vibe": {
        "rule_keys": {"event": "type", "matcher": "match"},
        "rule_name_prefix": "agentseam-",
        "default_match": "*",
        # strict = true only when install is called with fail_closed=True, and only at
        # pre_tool: HookConfig rejects it on post_agent (mistral-vibe 2.26.1 models.py).
        "fail_closed_rule": {"key": "strict", "events": ("pre_tool",)},
    },
    "vscode_copilot": {
        "entry_extra": {
            "bash": "the command as given",
            "powershell": "powershell wrapper (_windows.py)",
            "windows": "powershell wrapper (_windows.py)",
        }
    },
}


def _classify(agent, no_matcher, with_matcher):
    matcher_effective = no_matcher != with_matcher
    if isinstance(no_matcher, list):
        return dict({"wrapper": "flat_list", "matcher": matcher_effective}, **_EXTRA.get(agent, {}))
    if all(isinstance(value, str) for value in no_matcher.values()):
        return {"wrapper": "hook_dir", "matcher": matcher_effective}
    if "version" in no_matcher and "hooks" in no_matcher:
        return {"wrapper": "cursor", "matcher": matcher_effective}
    bare = False
    if "hooks" in no_matcher:
        table, group = no_matcher["hooks"], None
    else:
        # exactly one non-"hooks" wrapper key (antigravity's GROUP), or none (devin: no wrapper)
        keys = [k for k in no_matcher if isinstance(no_matcher[k], dict)]
        group, table = (keys[0], no_matcher[keys[0]]) if len(keys) == 1 else (None, no_matcher)
        bare = group is None
    grouped = {wire: "hooks" in entries[0] for wire, entries in table.items()}
    wrapper = "hooks_map" if any(grouped.values()) else "flat_entries"
    out = {"wrapper": wrapper, "matcher": matcher_effective}
    if wrapper == "hooks_map" and not all(grouped.values()):
        # antigravity: matcher-ignored events list their handlers bare, with no {matcher, hooks} group
        out["flat_events"] = sorted(wire for wire, has_group in grouped.items() if not has_group)
    defaults = {entries[0]["matcher"] for entries in table.values() if "matcher" in entries[0]}
    if wrapper == "hooks_map" and defaults:
        # the matcher hook_config() writes when the caller passes none
        (out["default_match"],) = defaults
    if bare:
        out["bare"] = True
    if group:
        out["group"] = group
    out.update(_EXTRA.get(agent, {}))
    return out


def hook_entry(agent):
    hc = _load_fixture(agent)["hook_config"]
    return _classify(agent, hc["no_matcher"], hc["with_matcher"]["config"])
