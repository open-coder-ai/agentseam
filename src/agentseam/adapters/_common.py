"""The settings.json hooks-fragment shape shared by adapters with no per-vendor wrinkle."""

from __future__ import annotations


def make_hook_config(reverse_event_map):
    """A `hook_config(canonical_events, command, matcher=None)` bound to one adapter's map."""

    def hook_config(canonical_events, command, matcher=None):
        """A settings.json `hooks` fragment wiring `command` for these canonical events."""
        hooks = {}
        for ev in canonical_events:
            name = reverse_event_map.get(ev)
            if not name:
                continue
            entry = {"hooks": [{"type": "command", "command": command}]}
            if matcher:
                entry["matcher"] = matcher
            hooks.setdefault(name, []).append(entry)
        return {"hooks": hooks}

    return hook_config
