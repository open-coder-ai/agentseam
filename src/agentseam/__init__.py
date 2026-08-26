"""agentseam — the primitives layer for every coding agent.

Write one handler; run it on Claude Code, Cursor, VS Code Copilot and friends.
agentseam owns the per-agent differences: payload shapes, response dialects, config
file formats, and an explicit capability matrix that says what each agent can
actually enforce.

    from agentseam import run, Decision

    def handler(event):
        if event.event == "pre_tool" and event.command == "rm -rf /":
            return Decision.deny("no")
        return Decision.allow()

    run(handler)
"""

from . import adapters, instructions, packaging, permissions
from .contract import (
    ALLOW,
    ASK,
    DENY,
    EVENTS,
    FILE_CHANGED,
    INSTRUCTIONS_LOADED,
    POST_TOOL,
    PRE_COMPACT,
    PRE_TOOL,
    PROMPT_SUBMIT,
    REWRITE,
    SESSION_END,
    SESSION_START,
    STOP,
    SUBAGENT_START,
    SUBAGENT_STOP,
    TOOL_FAILURE,
    Decision,
    Event,
)
from .dispatch import degrade, handle, run
from .matrix import MATRIX, adapted_agents, agents, can_block, can_rewrite, capability, enforcement_level

__version__ = "0.1.0"

__all__ = [
    "run",
    "handle",
    "degrade",
    "Event",
    "Decision",
    "EVENTS",
    "adapters",
    "instructions",
    "packaging",
    "permissions",
    "ALLOW",
    "DENY",
    "ASK",
    "REWRITE",
    "MATRIX",
    "agents",
    "capability",
    "can_block",
    "can_rewrite",
    "enforcement_level",
    "adapted_agents",
    "SESSION_START",
    "SESSION_END",
    "PROMPT_SUBMIT",
    "PRE_TOOL",
    "POST_TOOL",
    "TOOL_FAILURE",
    "PRE_COMPACT",
    "STOP",
    "SUBAGENT_START",
    "SUBAGENT_STOP",
    "INSTRUCTIONS_LOADED",
    "FILE_CHANGED",
    "__version__",
]
