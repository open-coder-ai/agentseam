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

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentseam import adapters  # noqa: E402
from agentseam.contract import PRE_TOOL  # noqa: E402

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


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_a_json_string_tool_input_reads_the_same_as_the_object(agent):
    """`tool_input` is not always an object, and the string form must not blind the guard.

    Witnessed live on VS Code Copilot (2026-08-29), same `Edit` tool in two runs routed to
    different models: once an object carrying path/old_str/new_str, once a 129-character
    JSON string. The object form parsed to a file and its content; the string form parsed
    to nothing, so a policy denying on secret content saw an empty write and allowed it.

    The isinstance guard added when `parse()` was made total stopped the crash -- and a
    crash is an allow -- but resolved the string to `{}`, which is the same blindness
    without the traceback.

    Stated as an equivalence rather than an assertion about fields, so it scopes itself: an
    adapter whose vendor does not use `tool_input` at all (antigravity reads PascalCase tool
    args, windsurf reads the top level) reads nothing from either shape and is not accused
    of a bug. What is forbidden is reading the object and not the string.
    """
    mod = adapters.get(agent)
    vendor_event = getattr(mod, "REVERSE_EVENT_MAP", {}).get(PRE_TOOL)
    if not vendor_event:
        pytest.skip("%s has no pre_tool gate" % agent)
    inner = {"path": "/repo/README.md", "file_path": "/repo/README.md", "old_str": "x", "new_str": "SECRET"}
    base = dict(
        conversation_id="c",
        generation_id="g",
        project_path="/repo",
        timestamp="t",
        prompt_id="p",
        turn_id="t",
        workspacePaths=["/repo"],
        hook_event_name=vendor_event,
        hookEventName=vendor_event,
        event=vendor_event,
        tool_name="Edit",
        toolName="Edit",
        client_type=agent,
    )
    as_object = mod.parse(dict(base, tool_input=inner))
    as_string = mod.parse(dict(base, tool_input=json.dumps(inner)))
    if not (as_object.path or as_object.content):
        pytest.skip("%s reads no path or content from tool_input" % agent)
    assert (as_string.path, as_string.content) == (as_object.path, as_object.content), (
        "%s read the object form but not the JSON-string form: object=(%r, %r) string=(%r, %r) "
        "-- a guard that cannot see the write allows it"
        % (agent, as_object.path, as_object.content, as_string.path, as_string.content)
    )
