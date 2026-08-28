"""`parse()` must not raise, whatever the payload looks like.

A guard that crashes is a guard that allows. `dispatch.run` wraps only the JSON decode --
everything after it, including `parse()`, runs unprotected -- so an exception here kills the
hook process with exit 1, and exit 1 is a non-blocking error on almost every vendor here.
The call proceeds. The one thing this library exists to prevent, caused by the library.

Six adapters crashed on a non-dict `tool_input` and three on an `edits` list containing
non-dicts, while five others already hardened with `isinstance` -- the inconsistency is what
made it invisible. `tool_input` is whatever the agent chose to serialise; its shape is not
ours to assume.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentseam import adapters  # noqa: E402

#: Shapes a payload could take that are not the one the adapter expects. Not exotic: a
#: vendor adding a scalar-argument tool, or a serialiser that flattens, produces these.
_HOSTILE = {
    "tool_input is a string": {"tool_input": "rm -rf /"},
    "tool_input is a list": {"tool_input": ["a"]},
    "tool_input is a number": {"tool_input": 7},
    "tool_input is null": {"tool_input": None},
    "edits holds non-dicts": {"tool_input": {"edits": ["oops", None, 3]}},
    "edits is not a list": {"tool_input": {"edits": "nope"}},
    "content is a dict": {"tool_input": {"content": {"nested": True}}},
    "tool_output is a list": {"tool_input": {}, "tool_output": [1, 2]},
    "no tool_input at all": {},
}


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
@pytest.mark.parametrize("label", sorted(_HOSTILE))
def test_parse_never_raises(agent, label):
    mod = adapters.get(agent)
    raw = dict(
        {
            "hook_event_name": "PreToolUse",
            "hookEventName": "preToolUse",
            "tool_name": "Write",
            "client_type": getattr(mod, "CLIENT_TYPE", None),
        },
        **_HOSTILE[label],
    )
    try:
        mod.parse(raw)
    except Exception as exc:  # noqa: BLE001 -- the whole point is that nothing escapes
        pytest.fail("%s.parse raised %s on %s: %s" % (agent, type(exc).__name__, label, exc))
