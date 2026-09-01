"""Bind a family engine to one vendor config entry, presenting the adapter-module surface."""

from __future__ import annotations

from . import _hook_json
from ._hook_entry import hook_entry_config, render_config
from ._hook_json import hj_respond, hj_reverse
from ._payload import hj_claims, hj_parse
from ._windows import powershell_command


class ConfigAdapter:
    """A module-like adapter: the hook_json engine closed over one `data/vendors` entry."""

    def __init__(self, cfg):
        self.CONFIG = cfg
        self.AGENT = cfg["agent"]
        self.EVENT_MAP = dict(cfg["events"])
        self.REVERSE_EVENT_MAP = hj_reverse(cfg)
        self.DECISION_VOCABULARY = frozenset(cfg["verdicts"]["vocabulary"])
        self.CONFIG_PATH = cfg["config_path"]
        self.CONFIG_FORMAT = cfg["config_format"]
        self.NEEDS_TRUST = cfg["needs_trust"]
        self.BLOCKING_EVENTS = tuple(cfg["verdicts"]["answer_events"])
        for attr, key in (("WRITE_TOOLS", "write"), ("SHELL_TOOLS", "shell"), ("MEMORY_TOOLS", "memory")):
            if cfg["tools"].get(key):
                setattr(self, attr, tuple(cfg["tools"][key]))
        client_types = cfg["claims"].get("client_types", ())
        if len(client_types) == 1 and client_types[0] is not None:
            self.CLIENT_TYPE = client_types[0]
        if cfg["config_format"] == "toml":
            self.render_config = render_config
        if any(key in _hook_entry_windows(cfg) for key in ("commandWindows", "windows")):
            self.powershell_command = powershell_command
        # The grep in test_decision_vocabulary reads the adapter's source file; for a
        # config-driven adapter that is the engine's.
        self.__file__ = _hook_json.__file__

    def claims(self, raw):
        return hj_claims(self.CONFIG, raw)

    def parse(self, raw):
        return hj_parse(self.CONFIG, raw)

    def respond(self, decision, event):
        return hj_respond(self.CONFIG, decision, event)

    def hook_config(self, canonical_events, command, matcher=None):
        return hook_entry_config(self.CONFIG, canonical_events, command, matcher)


def _hook_entry_windows(cfg):
    return tuple(cfg["hook_entry"].get("entry_extra", {}))


def bind(cfg):
    """The adapter object for one vendor config entry."""
    return ConfigAdapter(cfg)
