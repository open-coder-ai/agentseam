"""A bare ALLOW must land on whatever the vendor would have done with no hook at all."""

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
    """The vendor events that decide whether a TOOL CALL happens."""
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
    """Silent where silence is the vendor's abstention; spoken where it is not."""
    kind, _why = ALLOW_SEMANTICS[agent]
    wrong = []
    for vendor_event in _blocking_events(agent):
        text, code = _drive(agent, vendor_event)
        if kind == ALLOW_SILENT and text.strip():
            wrong.append("%s/%s asserted %r where silence is the vendor's own default" % (agent, vendor_event, text))
        assert code == 0, "%s/%s: a bare allow must never carry a non-zero exit" % (agent, vendor_event)
    for vendor_event in _permission_gates(agent):
        text, _code = _drive(agent, vendor_event)
        if kind != ALLOW_SILENT and not text.strip():
            wrong.append("%s/%s abstained, and silence is not an abstention on this vendor" % (agent, vendor_event))
    assert not wrong, "a bare ALLOW must mean the vendor's default:\n  " + "\n  ".join(wrong)


@pytest.mark.parametrize("agent", sorted(adapters.ADAPTERS))
def test_a_bare_allow_is_silent_wherever_no_verdict_is_read(agent):
    """Observation-only events have no permission flow to defer to, so approving there is"""
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
    """antigravity, devin and tabnine rest on documentation that does not answer the"""
    unsettled = sorted(a for a, (kind, _why) in ALLOW_SEMANTICS.items() if kind == ALLOW_UNVERIFIED)
    assert unsettled == ["antigravity", "devin", "tabnine"]


def test_vouch_speaks_only_where_the_word_is_actually_trusted():
    """Not every ALLOW_SILENT row: codex_cli is silent by the same default, but its own"""
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
    """dispatch.degrade() is where every other vendor's vouch is reduced -- one place, not"""
    event = Event(agent, PRE_TOOL)
    reduced = degrade(Decision.vouch("trusted"), event, agent)
    assert reduced.outcome == ALLOW
    assert reduced.evidence.get("degraded_from") == VOUCH
