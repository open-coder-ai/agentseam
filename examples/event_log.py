#!/usr/bin/env python3
"""Append every agent lifecycle event to one JSONL stream — across all your agents.

    agentseam install all "python3 examples/event_log.py" \
        --events pre_tool post_tool session_start stop

One timeline for Claude Code + Cursor + Copilot in the same repo: something no
single-agent logger can produce. Feed it to OTel, DuckDB, or just grep it.
"""

import json
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "src")
from agentseam import Decision, run  # noqa: E402

LOG = os.environ.get("AGENTSEAM_LOG", os.path.expanduser("~/.agentseam/events.jsonl"))


def handler(event):
    os.makedirs(os.path.dirname(LOG), exist_ok=True)
    record = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent": event.agent,
        "event": event.event,
        "tool": event.tool,
        "path": event.path,
        "session_id": event.session_id,
        # sizes, not contents: a log that copies file text becomes the leak it audits
        "content_len": len(event.content) if event.content else 0,
        "command_len": len(event.command) if event.command else 0,
    }
    with open(LOG, "a") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    return Decision.allow()


if __name__ == "__main__":
    run(handler)
