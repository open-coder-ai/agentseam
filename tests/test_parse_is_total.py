"""`parse()` must not raise, whatever the payload looks like."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import agentseam as A  # noqa: E402
from agentseam import adapters  # noqa: E402
from agentseam.contract import PRE_TOOL, UNKNOWN  # noqa: E402

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
    "tool_info is a string": {"trajectory_id": "t", "tool_info": "not an object"},
    "tool_input is a JSON string nested past the recursion limit": {"tool_input": "[" * 100_000},
}

#: Valid JSON documents that are not objects. `json.loads` hands every one of these to the
#: dispatcher, and each adapter's `parse` used to reach for `.get` on it.
_NOT_AN_OBJECT = {
    "a list": [],
    "a list of objects": [{"hook_event_name": "PreToolUse", "tool_name": "Bash"}],
    "a string": "PreToolUse",
    "a number": 1,
    "null": None,
}

#: An event key holding something other than text. Looking one of these up in the event map
#: raised `TypeError: unhashable type` -- out of `detect()` too, ahead of any handler.
_NOT_A_NAME = {
    "a list": ["PreToolUse"],
    "an object": {"name": "PreToolUse"},
    "a number": 7,
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
    """`tool_input` is not always an object, and the string form must not blind the guard."""
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


def _deny(_event):
    return A.Decision.deny("no")


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
@pytest.mark.parametrize("label", sorted(_NOT_AN_OBJECT))
def test_a_payload_that_is_not_an_object_is_unknown_not_a_crash(agent, label):
    """Named or detected, a non-object payload is the edge of our knowledge: allow, silently.

    Before: every adapter's `parse` raised AttributeError, so `run(handler, agent=...)` and
    every generated bundle died with a traceback -- exit 1, which the hosts read as a
    non-blocking error and carry on from. A crash here is a silent allow with noise.
    """
    raw = _NOT_AN_OBJECT[label]
    assert adapters.detect(raw) is None
    event = adapters.get(agent).parse(raw)
    assert event.event == UNKNOWN, "%s parsed %r as %s" % (agent, raw, event.event)
    text, code, _event, decision = A.handle(raw, _deny, agent=agent)
    assert (text, code, decision.outcome) == ("", 0, A.ALLOW)


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
@pytest.mark.parametrize("label", sorted(_NOT_A_NAME))
def test_an_event_name_that_is_not_text_is_unknown_not_a_crash(agent, label):
    mod = adapters.get(agent)
    # Only the key(s) this adapter reads: a name under any other key is simply absent to it,
    # and the shape-inferred families then answer at their default gate, as designed.
    cfg = getattr(mod, "CONFIG", None)
    keys = cfg["claims"].get("event_key", ("hook_event_name",)) if cfg else ("hook_event_name", "hookEventName")
    for key in keys:
        raw = {key: _NOT_A_NAME[label], "client_type": getattr(mod, "CLIENT_TYPE", None), "tool_name": "Bash"}
        adapters.detect(raw)  # must not raise, whichever adapter is asked
        event = mod.parse(raw)
        assert event.event == UNKNOWN, "%s parsed %r as %s" % (agent, raw, event.event)
        text, code, _event, decision = A.handle(raw, _deny, agent=agent)
        assert (text, code, decision.outcome) == ("", 0, A.ALLOW)


def test_a_self_identified_kimi_payload_with_an_unreadable_name_still_reaches_the_caller():
    """`accept_any_name` claims on the client_type alone; the name being unreadable is one
    more kind of unmapped, and the caller is told rather than left with no Event."""
    raw = {"hook_event_name": ["Stop"], "client_type": "kimi_code_cli", "session_id": "s"}
    assert adapters.detect(raw) == "kimi_code"
    _text, _code, event, _decision = A.handle(raw, _deny)
    assert event is not None and event.event == UNKNOWN
