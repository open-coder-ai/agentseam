"""agentshim — the primitives layer for every coding agent.

Write one handler; run it on Claude Code, Cursor, VS Code Copilot and friends.
agentshim owns the per-agent differences: payload shapes, response dialects, config
file formats, and an explicit capability matrix that says what each agent can
actually enforce.

    from agentshim import run, Decision

    def handler(event):
        if event.event == "pre_tool" and event.command == "rm -rf /":
            return Decision.deny("no")
        return Decision.allow()

    run(handler)
"""

from .contract import (Event, Decision, EVENTS, ALLOW, DENY, ASK, REWRITE,
                       SESSION_START, SESSION_END, PROMPT_SUBMIT, PRE_TOOL, POST_TOOL,
                       TOOL_FAILURE, PRE_COMPACT, STOP, SUBAGENT_START, SUBAGENT_STOP,
                       INSTRUCTIONS_LOADED, FILE_CHANGED)
from .dispatch import run, handle, degrade
from .matrix import (MATRIX, agents, capability, can_block, can_rewrite,
                     enforcement_level)
from . import adapters

__version__ = "0.1.0"

__all__ = [
    "run", "handle", "degrade", "Event", "Decision", "EVENTS", "adapters",
    "ALLOW", "DENY", "ASK", "REWRITE",
    "MATRIX", "agents", "capability", "can_block", "can_rewrite", "enforcement_level",
    "SESSION_START", "SESSION_END", "PROMPT_SUBMIT", "PRE_TOOL", "POST_TOOL",
    "TOOL_FAILURE", "PRE_COMPACT", "STOP", "SUBAGENT_START", "SUBAGENT_STOP",
    "INSTRUCTIONS_LOADED", "FILE_CHANGED", "__version__",
]
