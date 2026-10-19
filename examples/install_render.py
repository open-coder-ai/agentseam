"""What `agentseam install` writes, rendered for a page in the config's own format."""

from __future__ import annotations

import json

from agentseam.install_config import bind_agent, mark, unwatched
from agentseam.install_hook_dir import script


def _fence(text, lang=""):
    return "```%s\n%s\n```" % (lang, text.rstrip("\n"))


def install_section(mod, events, command):
    """What `install` writes for these events: the events it leaves out dropped and named, and
    a JSON config's entries carrying the ownership marker exactly as `install` puts it."""
    events, left_out = unwatched(mod, mod.AGENT, events, None)
    config = mod.hook_config(events, bind_agent(command, mod.AGENT))
    if getattr(mod, "CONFIG_FORMAT", "json") == "json":
        config = mark(config, "agentseam")
    return install_body(mod, config) + ("\n\n%s.\n" % left_out if left_out else "")


def install_body(mod, config):
    """The hook config as a fenced block, or one fenced script per file for a hooks directory."""
    fmt = getattr(mod, "CONFIG_FORMAT", "json")
    if fmt == "hook_dir":
        return "\n".join(
            "`%s/%s` (executable)\n\n%s\n" % (mod.CONFIG_PATH, name, _fence(script(command, "agentseam"), "sh"))
            for name, command in config.items()
        )
    if fmt == "toml":
        return _fence(mod.render_config(config), "toml")
    return _fence(json.dumps(config, indent=2, sort_keys=True), "json")
