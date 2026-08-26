#!/usr/bin/env python3
"""Desktop notification when an agent finishes or needs you — on ANY agent.

    agentseam install all "python3 examples/notify.py" --events stop prompt_submit

Highest-breadth hook use case in the wild, normally re-written per agent. Here it is
agent-agnostic in ten lines.
"""

import subprocess
import sys

sys.path.insert(0, "src")
from agentseam import Decision, run  # noqa: E402


def notify(title, message):
    for cmd in (
        ["notify-send", title, message],
        ["osascript", "-e", 'display notification "%s" with title "%s"' % (message, title)],
    ):
        try:
            subprocess.run(cmd, check=False, capture_output=True)
            return
        except FileNotFoundError:
            continue
    print("%s: %s" % (title, message), file=sys.stderr)  # fallback: stderr


def handler(event):
    if event.event == "stop":
        notify("Agent finished", "%s is done" % event.agent)
    elif event.event == "prompt_submit":
        notify("Agent working", (event.prompt or "")[:80])
    return Decision.allow()


if __name__ == "__main__":
    run(handler)
