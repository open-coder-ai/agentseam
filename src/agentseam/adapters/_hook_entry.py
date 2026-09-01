"""Hook-config renderers for config-driven adapters, selected by the entry's `hook_entry`."""

from __future__ import annotations

from ._hook_json import hj_reverse
from ._windows import powershell_command

#: entry_extra keys that carry a PowerShell-callable copy of the command. In a bundle,
#: `powershell_command` is inlined only for vendors whose entry_extra names one of these;
#: elsewhere the branch below is unreachable because entry_extra is empty.
_WINDOWS_KEYS = ("commandWindows", "windows")


def _hook_dict(cfg, command):
    entry = {"type": "command", "command": command}
    for key in cfg["hook_entry"].get("entry_extra", {}):
        if key in _WINDOWS_KEYS:
            entry[key] = powershell_command(command)
    return entry


def hook_entry_config(cfg, canonical_events, command, matcher=None):
    """The vendor's hooks-config fragment wiring `command` for these canonical events."""
    hook_entry = cfg["hook_entry"]
    reverse = hj_reverse(cfg)
    if hook_entry["wrapper"] == "flat_list":
        rules = []
        for ev in canonical_events:
            name = reverse.get(ev)
            if not name:
                continue
            rule = {"event": name, "command": command}
            if matcher and hook_entry["matcher"]:
                rule["matcher"] = matcher
            rules.append(rule)
        return rules
    hooks = {}
    for ev in canonical_events:
        name = reverse.get(ev)
        if not name:
            continue
        entry = {"hooks": [_hook_dict(cfg, command)]}
        if matcher and hook_entry["matcher"]:
            entry["matcher"] = matcher
        hooks.setdefault(name, []).append(entry)
    return hooks if hook_entry.get("bare") else {"hooks": hooks}


def _toml_value(value):
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return '"%s"' % escaped


def render_config(rules):
    """Emit `[[hooks]]` tables. Only the four documented fields, in a documented order."""
    blocks = []
    for rule in rules:
        lines = ["[[hooks]]"]
        for key in ("event", "matcher", "command", "timeout"):
            if rule.get(key) is not None:
                lines.append("%s = %s" % (key, _toml_value(rule[key])))
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks) + "\n"
