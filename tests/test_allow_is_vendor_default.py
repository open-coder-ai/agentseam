"""A bare ALLOW must land on whatever the vendor would have done with no hook at all.

The fifth invariant, and the one with the worst defect behind it. "The handler has no
objection" and "skip the user's confirmation" are different statements, and adapters were
spelling the first as the second. On VS Code Copilot that is not a nuance:
languageModelToolsService returns `autoConfirmed: ConfirmationNotNeeded` on
permissionDecision:"allow", so a policy that simply did not match -- which is the common
case, on every tool call of every turn -- was switching off the user's own permission
prompts for the whole session. The guardrail was the thing removing the protection.

That was fixed on the two adapters where it was established. The audit of the other ten
found the split was accidental everywhere: six silent, six speaking, nothing recording which
was meant. `allow_semantics.ALLOW_SEMANTICS` is that audit, and this is the test that keeps
the code and the audit from drifting apart.

The rule is not "always be silent". Silence is not universally available: on Cursor an empty
response was witnessed to REJECT the call, so an adapter that abstained there would block the
user's work on every tool call -- the opposite failure, equally caused by assuming one
vendor's semantics are all vendors'. Hence four kinds rather than a boolean.

Like its siblings, this checks the code against what the repository records, not against
reality. A vendor disagreeing with its own documentation is a job for a live session; a
vendor disagreeing with our source is a job for CI, and that is this file.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentseam import MATRIX, Decision, adapters  # noqa: E402
from agentseam.allow_semantics import (  # noqa: E402
    ALLOW_INERT,
    ALLOW_REQUIRED,
    ALLOW_SEMANTICS,
    ALLOW_SILENT,
    ALLOW_UNVERIFIED,
    VOUCH_SPEAKS,
)
from agentseam.contract import ALLOW, PRE_TOOL, VOUCH, Event  # noqa: E402
from agentseam.dispatch import degrade  # noqa: E402

_KINDS = (ALLOW_SILENT, ALLOW_INERT, ALLOW_REQUIRED, ALLOW_UNVERIFIED)

#: Carries every discriminator the adapters key on, so one payload parses as whichever
#: vendor is under test.
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
    "workspacePaths": ["/repo"],
}


def _drive(agent, vendor_event):
    """respond() to a bare ALLOW at one vendor event name."""
    mod = adapters.get(agent)
    raw = dict(_PROBE_PAYLOAD, hook_event_name=vendor_event, hookEventName=vendor_event, client_type=agent)
    return mod.respond(Decision.allow(), mod.parse(raw))


def _blocking_events(agent):
    """Vendor event names whose canonical event the matrix says can block."""
    mod = adapters.get(agent)
    return sorted(
        name
        for name, canonical in getattr(mod, "EVENT_MAP", {}).items()
        if (MATRIX[agent]["events"].get(canonical) or {}).get("block")
    )


def _permission_gates(agent):
    """The vendor events that decide whether a TOOL CALL happens.

    ALLOW_SEMANTICS is a claim about the permission flow, and only pre_tool is that flow.
    The distinction is not pedantic: junie's Stop takes the same allow/block vocabulary but
    means "keep working" / "you may finish", so abstaining there is exactly the vendor
    default even though abstaining at its permission gate is not. Asking one question of
    both events called that correct behaviour a bug.
    """
    mod = adapters.get(agent)
    blocks = (MATRIX[agent]["events"].get(PRE_TOOL) or {}).get("block")
    if not blocks:
        return []
    return sorted(name for name, canonical in getattr(mod, "EVENT_MAP", {}).items() if canonical == PRE_TOOL)


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_every_adapter_records_what_a_bare_allow_means_to_its_vendor(agent):
    """An adapter absent from the audit cannot be checked, so the absence is the failure."""
    assert agent in ALLOW_SEMANTICS, "%s must record what a bare ALLOW means -- see allow_semantics" % agent
    kind, why = ALLOW_SEMANTICS[agent]
    assert kind in _KINDS, "%s declares an unknown kind %r" % (agent, kind)
    assert why.strip(), "%s must record the evidence, not just the verdict" % agent


def test_the_audit_covers_the_adapters_that_exist_and_no_others():
    """A row for a deleted adapter is stale evidence, which is worse than none."""
    assert sorted(ALLOW_SEMANTICS) == sorted(adapters.ADAPTERS)


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_a_bare_allow_matches_what_the_vendor_reads(agent):
    """Silent where silence is the vendor's abstention; spoken where it is not.

    Driven over every vendor event name the adapter maps whose canonical event the matrix
    says can block -- the aliases included, since a second name for one canonical event is
    exactly where the sibling invariants have found adapters behaving two ways at once.
    """
    kind, _why = ALLOW_SEMANTICS[agent]
    wrong = []
    # The silence half is checked at EVERY blocking event: an adapter recorded as abstaining
    # must not turn out to assert an approval at some alias of one of its gates.
    for vendor_event in _blocking_events(agent):
        text, code = _drive(agent, vendor_event)
        if kind == ALLOW_SILENT and text.strip():
            wrong.append("%s/%s asserted %r where silence is the vendor's own default" % (agent, vendor_event, text))
        assert code == 0, "%s/%s: a bare allow must never carry a non-zero exit" % (agent, vendor_event)
    # The speech half is checked only at the permission gate -- see _permission_gates.
    for vendor_event in _permission_gates(agent):
        text, _code = _drive(agent, vendor_event)
        if kind != ALLOW_SILENT and not text.strip():
            wrong.append("%s/%s abstained, and silence is not an abstention on this vendor" % (agent, vendor_event))
    assert not wrong, "a bare ALLOW must mean the vendor's default:\n  " + "\n  ".join(wrong)


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_a_bare_allow_is_silent_wherever_no_verdict_is_read(agent):
    """Observation-only events have no permission flow to defer to, so approving there is
    pure noise -- and noise is not free: on Tabnine stdout that is not the expected JSON is
    treated as a systemMessage and the action allowed, so a stray approval is a parse the
    vendor resolves in favour of running the call.
    """
    mod = adapters.get(agent)
    blocking = set(_blocking_events(agent))
    noisy = []
    for vendor_event in sorted(getattr(mod, "EVENT_MAP", {})):
        if vendor_event in blocking:
            continue
        text, _code = _drive(agent, vendor_event)
        if text.strip():
            noisy.append("%s/%s (detect-only) answered a bare allow with %r" % (agent, vendor_event, text))
    assert not noisy, "a bare allow at an event that reads no verdict:\n  " + "\n  ".join(noisy)


def test_the_unsettled_rows_are_still_exactly_these_three():
    """antigravity, devin and tabnine rest on documentation that does not answer the
    question, and are left as found rather than moved on a guess. Pinning the set makes
    closing one a deliberate, visible diff instead of a silent reclassification -- and makes
    ADDING one impossible to do quietly, which is the direction that would actually hurt.
    """
    unsettled = sorted(a for a, (kind, _why) in ALLOW_SEMANTICS.items() if kind == ALLOW_UNVERIFIED)
    assert unsettled == ["antigravity", "devin", "tabnine"]


def test_vouch_speaks_only_where_the_word_is_actually_trusted():
    """Not every ALLOW_SILENT row: codex_cli is silent by the same default, but its own
    evidence says the explicit word is REJECTED (a hook error, which fails open) rather than
    honoured. Speaking it there would be the opposite of "skip confirmation" -- pinned so a
    mechanical `kind == ALLOW_SILENT` derivation cannot quietly resurrect that bug.
    """
    assert VOUCH_SPEAKS == {"claude_code", "vscode_copilot"}
    for agent in VOUCH_SPEAKS:
        assert ALLOW_SEMANTICS[agent][0] == ALLOW_SILENT, agent


@pytest.mark.parametrize("agent", sorted(VOUCH_SPEAKS))
def test_vouch_speaks_the_same_word_allow_withholds(agent):
    """The one place a bare ALLOW is deliberately silent is exactly where VOUCH must not be."""
    for vendor_event in _permission_gates(agent):
        allow_text, _ = _drive(agent, vendor_event)
        assert not allow_text.strip(), "bare allow must still be silent at %s/%s" % (agent, vendor_event)
        mod = adapters.get(agent)
        raw = dict(_PROBE_PAYLOAD, hook_event_name=vendor_event, hookEventName=vendor_event, client_type=agent)
        vouch_text, code = mod.respond(Decision.vouch("trusted"), mod.parse(raw))
        assert vouch_text.strip(), "%s/%s: vouch must speak where allow_semantics trusts it" % (agent, vendor_event)
        assert code == 0


@pytest.mark.parametrize("agent", sorted(a for a in adapters.ADAPTERS if a not in VOUCH_SPEAKS))
def test_vouch_degrades_to_an_honestly_labelled_allow_elsewhere(agent):
    """dispatch.degrade() is where every other vendor's vouch is reduced -- one place, not
    thirteen copies of the same check -- and the reduction must say what it was."""
    event = Event(agent, PRE_TOOL)
    reduced = degrade(Decision.vouch("trusted"), event, agent)
    assert reduced.outcome == ALLOW
    assert reduced.evidence.get("degraded_from") == VOUCH
