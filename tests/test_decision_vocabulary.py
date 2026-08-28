"""Every decision word an adapter emits must be one its vendor accepts.

This is the guardrail for a defect class this project keeps finding by hand. A `respond()`
that emits a word the vendor's parser does not recognise is not a louder refusal -- most of
these agents fail OPEN, so an unrecognised decision is a *permitted action*, reported to the
caller as a block. Two instances were found by inspection in 2026-08:

  * junie emitted "deny" where the vendor's vocabulary is allow/ask/block, at all three of
    its permission gates.
  * claude_code emitted permissionDecision at prompt_submit and stop, which read a top-level
    "block" instead -- so every deny there was discarded.

Both were invisible to the rest of the suite, which asserted the *shape* of a response and
never asked whether the vendor had a word for it. A per-adapter `DECISION_VOCABULARY`, cited
to where the value is recorded, plus this test, turns that from something a human has to
notice into something CI refuses to merge.

The vocabularies are claims about vendors and can be wrong -- tabnine's is explicitly
unverified. This test does not check them against reality; it checks the code against them,
so a disagreement is at least visible in one place instead of buried in a branch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from scenarios import SCENARIOS  # noqa: E402

from agentseam import Decision, adapters  # noqa: E402

#: Keys whose string value is a decision, wherever they sit in the response. Adapters put
#: them at the top level, inside hookSpecificOutput, or under `permission` -- the point of
#: walking the whole object is that a new nesting cannot smuggle a word past this test.
_DECISION_KEYS = ("decision", "permission", "permissionDecision")

_OUTCOMES = (
    ("allow", lambda: Decision.allow()),
    ("deny", lambda: Decision.deny("policy")),
    ("ask", lambda: Decision.ask("confirm")),
    ("rewrite", lambda: Decision.rewrite({"content": "safe"}, "redacted")),
    # A rewrite with nothing to substitute is the degradation path, and degradation is where
    # a wrong word is most likely: the adapter has to pick a verb it was not handed.
    ("rewrite-without-input", lambda: Decision.rewrite(None, "needs change")),
)


def _words(out):
    """Every decision word in this response, at any depth."""
    found = set()
    if not out:
        return found
    try:
        body = json.loads(out)
    except ValueError:
        return found  # a non-JSON response carries no decision word to check
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
    """Driven over every event the agent claims and every outcome a handler can return.

    SCENARIOS rather than the fixture list on purpose: it is built from the matrix, so it
    covers exactly the events each agent is advertised as supporting. An adapter cannot pass
    this by simply having no payload for its weakest event.
    """
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
    """One vocabulary here rests on nothing recorded: tabnine's. That is a known gap with a
    backlog entry, deliberately left rather than guessed at -- swapping to an equally
    unrecorded word would trade one guess for another.

    Pinned so the exception cannot quietly spread. A second unverified vocabulary should be
    a decision someone makes on purpose, not a thing that drifts in.
    """
    unverified = {
        agent for agent in sorted(adapters.ADAPTERS) if "UNVERIFIED" in (Path(adapters.get(agent).__file__).read_text())
    }
    assert unverified == {"tabnine"}, unverified
