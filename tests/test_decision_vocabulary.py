"""What `respond()` may say, and where it may say it."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from scenarios import SCENARIOS  # noqa: E402

from agentseam import MATRIX, Decision, adapters  # noqa: E402

_DECISION_KEYS = ("decision", "permission", "permissionDecision")

_PROBE_PAYLOAD = {
    "prompt_id": "p",
    "turn_id": "t",
    "timestamp": "2026-08-28T00:00:00Z",
    "project_path": "/repo",
    "conversation_id": "c",
    "generation_id": "g",
    "transcript_path": "/t.jsonl",
    "tool_name": "x",
    "tool_input": {"command": "c"},
    "prompt": "p",
}

_OUTCOMES = (
    ("allow", lambda: Decision.allow()),
    ("deny", lambda: Decision.deny("policy")),
    ("ask", lambda: Decision.ask("confirm")),
    ("rewrite", lambda: Decision.rewrite({"content": "safe"}, "redacted")),
    ("rewrite-without-input", lambda: Decision.rewrite(None, "needs change")),
    ("vouch", lambda: Decision.vouch("trusted")),
)


def _words(out):
    """Every decision word in this response, at any depth."""
    found = set()
    if not out:
        return found
    try:
        body = json.loads(out)
    except ValueError:
        return found
    stack = [body]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key in _DECISION_KEYS and isinstance(value, str):
                    found.add(value)
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return found


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_every_adapter_declares_the_words_its_vendor_accepts(agent):
    """An adapter with no declaration cannot be checked, so the absence is the failure."""
    vocabulary = getattr(adapters.get(agent), "DECISION_VOCABULARY", None)
    assert isinstance(vocabulary, frozenset), "%s must declare DECISION_VOCABULARY" % agent


@pytest.mark.parametrize("agent", sorted(SCENARIOS))
def test_respond_never_emits_a_word_its_vendor_does_not_accept(agent):
    """Driven over every event the agent claims and every outcome a handler can return."""
    mod = adapters.get(agent)
    vocabulary = mod.DECISION_VOCABULARY
    violations = []
    for event, raw in sorted(SCENARIOS[agent].items()):
        parsed = mod.parse(raw)
        for label, make in _OUTCOMES:
            text, _code = mod.respond(make(), parsed)
            for word in sorted(_words(text) - vocabulary):
                violations.append("%s at %s on %s -> %r" % (agent, event, label, word))
    assert not violations, "decision words no recorded vendor vocabulary accepts:\n  " + "\n  ".join(violations)


def test_the_unverified_vocabulary_is_still_only_tabnine():
    """One vocabulary here rests on nothing recorded: tabnine's. That is a known gap with a"""
    unverified = {
        agent for agent in sorted(adapters.ADAPTERS) if "UNVERIFIED" in (Path(adapters.get(agent).__file__).read_text())
    }
    assert unverified == {"tabnine"}, unverified


@pytest.mark.parametrize("agent", sorted(SCENARIOS))
def test_respond_speaks_a_verdict_only_where_the_matrix_says_one_is_read(agent):
    """A decision word at a detect-only event is a refusal nobody reads."""
    mod = adapters.get(agent)
    events = MATRIX[agent]["events"]
    spurious = []
    for event, raw in sorted(SCENARIOS[agent].items()):
        if (events.get(event) or {}).get("block"):
            continue
        text, _code = mod.respond(Decision.deny("policy"), mod.parse(raw))
        for word in sorted(_words(text)):
            spurious.append("%s/%s (detect-only) -> %r" % (agent, event, word))
    assert not spurious, "verdicts at events the matrix says cannot block:\n  " + "\n  ".join(spurious)


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_a_deny_at_a_blocking_event_is_never_silent(agent):
    """Silence at a gate is the dispatcher's allow. This drives EVERY vendor event name,"""
    mod = adapters.get(agent)
    silent = []
    for vendor_event, canonical in sorted(getattr(mod, "EVENT_MAP", {}).items()):
        if not (MATRIX[agent]["events"].get(canonical) or {}).get("block"):
            continue
        raw = dict(_PROBE_PAYLOAD, hook_event_name=vendor_event, hookEventName=vendor_event, client_type=agent)
        text, code = mod.respond(Decision.deny("policy"), mod.parse(raw))
        if not text.strip() and code == 0:
            silent.append("%s/%s (-> %s) answered a deny with silence" % (agent, vendor_event, canonical))
    assert not silent, "a deny at a blocking event must not be silent:\n  " + "\n  ".join(silent)
