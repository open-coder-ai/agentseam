"""What `respond()` may say, and where it may say it.

Two invariants, both checking the code against what this repository records about each
vendor -- the class of defect that has to be found by inspection otherwise.

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

The second invariant asks a different question: not which words, but at which events. An
adapter that answers everywhere speaks a verdict at events the vendor never reads one from,
and that found two more defects when it was written -- devin and gemini_cli both returned a
full block/deny at their observation-only events, contradicting their own matrix rows.

Neither invariant checks the recorded claims against reality; they check the code against
the claims, so a disagreement is visible in one place instead of buried in a branch.
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

from agentseam import MATRIX, Decision, adapters  # noqa: E402

#: Keys whose string value is a decision, wherever they sit in the response. Adapters put
#: them at the top level, inside hookSpecificOutput, or under `permission` -- the point of
#: walking the whole object is that a new nesting cannot smuggle a word past this test.
_DECISION_KEYS = ("decision", "permission", "permissionDecision")

#: Carries every discriminator the adapters key on, so one payload parses as whichever
#: vendor is under test. Only the event name and agent vary per call.
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


@pytest.mark.parametrize("agent", sorted(SCENARIOS))
def test_respond_speaks_a_verdict_only_where_the_matrix_says_one_is_read(agent):
    """A decision word at a detect-only event is a refusal nobody reads.

    Worse than useless: it invites a log, a capture, or a downstream consumer to record a
    block that never happened, and it is indistinguishable on the wire from a real gate
    verdict. The matrix row is this project's own recorded claim about which events can
    block, so an adapter answering outside it contradicts its own documentation.

    Found devin (post_tool, session_start, session_end) and gemini_cli (pre_compact,
    session_start, session_end) when first written -- both open items in the vendor-truth
    backlog, both filed 'certain', neither previously caught by a test.

    The converse -- silence at a BLOCKING event -- is not asserted here: several adapters
    legitimately answer an allow with silence, which is the correct spelling of "proceed"
    in more than one dialect.
    """
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


#: Vendor events that map onto a blocking canonical event but cannot actually block, so a
#: deny there is dropped in silence. This is `kimi_code.py:~50` in the vendor-truth backlog:
#: the vendor documents exactly three blocking events (PreToolUse, UserPromptSubmit, Stop)
#: and these four are fire-and-forget, yet they alias onto canonical events the matrix rates
#: blocking. Fixing it is a design choice -- unmap them and lose the lifecycle signal, or
#: correct the matrix claim -- so it is pinned here rather than resolved by guess. Pinned,
#: not ignored: the gap is visible in CI and a NEW silent gate still fails.
_SILENT_GATES = {
    ("kimi_code", "UserPromptQueued"),
    ("kimi_code", "PermissionRequest"),
    ("kimi_code", "StopFailure"),
    ("kimi_code", "Interrupt"),
}


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_a_deny_at_a_blocking_event_is_never_silent(agent):
    """Silence at a gate is the dispatcher's allow. This drives EVERY vendor event name,
    not just the shipping corpus, because the corpus only exercises each canonical event's
    primary vendor name -- and the aliases are exactly where this hides.

    It exists because writing the sibling invariant above introduced this very bug: scoping
    devin's respond() to a blocking-events tuple silently dropped PermissionRequest, which
    maps to canonical pre_tool. A deny at a permission gate began returning "" -- an allow.
    Caught by re-reading the diff, which is not a reliable enough net to leave it at.

    "Said something" rather than "used a decision word" on purpose: cursor refuses at
    beforeSubmitPrompt with {"continue": false} and no decision word at all, which is a real
    block in that dialect. Testing for a word would have called that a bug.
    """
    mod = adapters.get(agent)
    silent = []
    for vendor_event, canonical in sorted(getattr(mod, "EVENT_MAP", {}).items()):
        if not (MATRIX[agent]["events"].get(canonical) or {}).get("block"):
            continue
        if (agent, vendor_event) in _SILENT_GATES:
            continue
        raw = dict(_PROBE_PAYLOAD, hook_event_name=vendor_event, hookEventName=vendor_event, client_type=agent)
        text, code = mod.respond(Decision.deny("policy"), mod.parse(raw))
        if not text.strip() and code == 0:
            silent.append("%s/%s (-> %s) answered a deny with silence" % (agent, vendor_event, canonical))
    assert not silent, "a deny at a blocking event must not be silent:\n  " + "\n  ".join(silent)


def test_the_pinned_silent_gates_are_still_silent():
    """A pinned exception must expire when it stops being true, or it outlives the defect
    and quietly excuses a future one at the same coordinates."""
    for agent, vendor_event in sorted(_SILENT_GATES):
        mod = adapters.get(agent)
        raw = dict(_PROBE_PAYLOAD, hook_event_name=vendor_event, client_type=agent)
        text, code = mod.respond(Decision.deny("policy"), mod.parse(raw))
        assert not text.strip() and code == 0, "%s/%s now answers -- drop it from _SILENT_GATES" % (
            agent,
            vendor_event,
        )
