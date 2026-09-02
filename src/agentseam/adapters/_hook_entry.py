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
    for key, value in cfg["hook_entry"].get("entry_extra", {}).items():
        if key in _WINDOWS_KEYS:
            entry[key] = powershell_command(command)
        else:
            entry[key] = value
    return entry


def _flat_list_wrapper(hook_entry, reverse, canonical_events, command, matcher):
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


def _cursor_wrapper(cfg, reverse, canonical_events, command, *, fail_closed):
    gates = cfg["verdicts"]["answer_events"]
    hooks = {}
    for ev in canonical_events:
        name = reverse.get(ev)
        if not name:
            continue
        entry = {"command": command}
        if fail_closed and name in gates:
            entry["failClosed"] = True
        hooks.setdefault(name, []).append(entry)
    return {"version": 1, "hooks": hooks}


def _flat_entries_wrapper(hook_entry, reverse, canonical_events, command):
    hooks = {}
    for ev in canonical_events:
        name = reverse.get(ev)
        if not name:
            continue
        hooks.setdefault(name, []).append({"command": command})
        extra = hook_entry.get("also_wires", {}).get(ev)
        if extra:
            hooks.setdefault(extra, []).append({"command": command})
    return {"hooks": hooks}


def _default_wrapper(cfg, reverse, canonical_events, command, matcher):
    hook_entry = cfg["hook_entry"]
    hooks = {}
    for ev in canonical_events:
        name = reverse.get(ev)
        if not name:
            continue
        entry = {"hooks": [_hook_dict(cfg, command)]}
        if matcher and hook_entry["matcher"]:
            entry["matcher"] = matcher
        hooks.setdefault(name, []).append(entry)
    if hook_entry.get("group"):
        return {hook_entry["group"]: hooks}
    return hooks if hook_entry.get("bare") else {"hooks": hooks}


def hook_entry_config(cfg, canonical_events, command, matcher=None, *, fail_closed=True):
    """The vendor's hooks-config fragment wiring `command` for these canonical events.

    `fail_closed` is read only by the `cursor` wrapper, whose gates fail open unless the
    entry says otherwise; a False installs an observer, not a gate.
    """
    hook_entry = cfg["hook_entry"]
    reverse = hj_reverse(cfg)
    wrapper = hook_entry["wrapper"]
    if wrapper == "flat_list":
        return _flat_list_wrapper(hook_entry, reverse, canonical_events, command, matcher)
    if wrapper == "cursor":
        return _cursor_wrapper(cfg, reverse, canonical_events, command, fail_closed=fail_closed)
    if wrapper == "flat_entries":
        return _flat_entries_wrapper(hook_entry, reverse, canonical_events, command)
    return _default_wrapper(cfg, reverse, canonical_events, command, matcher)


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
