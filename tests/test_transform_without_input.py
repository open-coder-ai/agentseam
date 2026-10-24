"""A transform that carries no replacement input is refused at every gate, never passed through."""

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentseam import Decision, adapters, dispatch  # noqa: E402

GOLDEN = ROOT / "tests" / "fixtures" / "golden"


def _pre_tool(agent):
    return json.loads((GOLDEN / ("%s.json" % agent)).read_text(encoding="utf-8"))["events"]["pre_tool"]["payload"]


def _keys(node):
    if isinstance(node, dict):
        for key, value in node.items():
            yield key
            yield from _keys(value)


def _values(node):
    if isinstance(node, dict):
        for value in node.values():
            yield from _values(value)
    else:
        yield node


def _assert_refused(text):
    out = json.loads(text) if text.startswith("{") else {}
    assert "null" not in text
    assert not set(_keys(out)) & {"updatedInput", "tool_input", "updated_input"}
    assert "allow" not in _values(out)


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_dispatch_never_passes_an_empty_transform_through(agent):
    text, _code, _event, _decision = dispatch.handle(_pre_tool(agent), lambda _e: Decision.transform(None, "x"), agent)
    _assert_refused(text)


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_an_adapter_never_renders_a_null_replacement_input(agent):
    mod = adapters.get(agent)
    event = mod.parse(_pre_tool(agent))
    text, _code = mod.respond(Decision.transform(None, "x"), event)
    _assert_refused(text)
