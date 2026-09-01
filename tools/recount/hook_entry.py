"""Executed against the D1 golden fixture: the `hook_config()` wrapper shape."""

from __future__ import annotations

from .gates import _load_fixture

_EXTRA = {
    # Event wiring, not an entry field: pre_mcp_tool_use is wired BESIDE pre_run_command
    # whenever pre_tool is (windsurf.py:106-107), so it must not be copied into entries.
    "windsurf": {"also_wires": {"pre_tool": "pre_mcp_tool_use"}},
    "codex_cli": {"entry_extra": {"commandWindows": "powershell wrapper (_windows.py)"}},
    "tabnine": {"entry_extra": {"name": "agentseam"}},
    "vscode_copilot": {"entry_extra": {"windows": "powershell wrapper (_windows.py)"}},
}


def _classify(agent, no_matcher, with_matcher):
    matcher_effective = no_matcher != with_matcher
    if isinstance(no_matcher, list):
        return {"wrapper": "flat_list", "matcher": matcher_effective}
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
    sample = next(iter(table.values()))[0]
    wrapper = "hooks_map" if "hooks" in sample else "flat_entries"
    out = {"wrapper": wrapper, "matcher": matcher_effective}
    if bare:
        out["bare"] = True
    if group:
        out["group"] = group
    out.update(_EXTRA.get(agent, {}))
    return out


def hook_entry(agent):
    hc = _load_fixture(agent)["hook_config"]
    return _classify(agent, hc["no_matcher"], hc["with_matcher"]["config"])
