"""D2 §3.1: the `claims` section describes a subset of `claims()` -- markers, not a spec.

Every marker/value recorded in `data/vendors/<agent>.json`'s `claims` is checked here by
mutating a REAL, already-claimed payload (frozen by D1's golden fixture) and replaying the
adapter's own `claims()` -- a wrong marker in the config fails this test.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentseam import adapters  # noqa: E402
from agentseam.vendor_config import VENDOR_CONFIG  # noqa: E402

FIXTURE_DIR = ROOT / "tests" / "fixtures" / "golden"

MARKER_AGENTS = sorted(a for a in adapters.ADAPTERS if VENDOR_CONFIG[a]["claims"]["mode"] == "marker")


def _sample_payload(agent):
    """A real payload this adapter genuinely claims, frozen by D1."""
    fixture = json.loads((FIXTURE_DIR / ("%s.json" % agent)).read_text(encoding="utf-8"))
    event = next(iter(sorted(fixture["events"])))
    payload = fixture["events"][event]["payload"]
    assert adapters.get(agent).claims(payload), "%s: fixture sample is not even self-claimed" % agent
    return payload


@pytest.mark.parametrize("agent", MARKER_AGENTS)
def test_reject_markers_actually_reject(agent):
    """Adding a declared reject marker to a real claimed payload must turn claims() False."""
    mod = adapters.get(agent)
    payload = _sample_payload(agent)
    for marker in VENDOR_CONFIG[agent]["claims"].get("reject_markers", ()):
        mutated = dict(payload, **{marker: "probe-value"})
        assert not mod.claims(mutated), "%s: reject_marker %r did not reject" % (agent, marker)


@pytest.mark.parametrize("agent", MARKER_AGENTS)
def test_accept_markers_are_actually_required(agent):
    """Deleting a declared required marker from a real claimed payload must turn claims() False."""
    mod = adapters.get(agent)
    payload = _sample_payload(agent)
    for marker in VENDOR_CONFIG[agent]["claims"].get("accept_markers", ()):
        if marker not in payload:
            continue  # marker was satisfied some other way in this sample; not this test's job
        mutated = {k: v for k, v in payload.items() if k != marker}
        assert not mod.claims(mutated), "%s: accept_marker %r was not actually required" % (agent, marker)


@pytest.mark.parametrize("agent", MARKER_AGENTS)
def test_accept_names_are_accepted_unconditionally(agent):
    """A declared accept_name is claimed on its own, with no marker to lean on."""
    mod = adapters.get(agent)
    for name in VENDOR_CONFIG[agent]["claims"].get("accept_names", ()):
        assert mod.claims({"hook_event_name": name}), "%s: accept_name %r was not claimed" % (agent, name)


@pytest.mark.parametrize("agent", MARKER_AGENTS)
def test_reject_markers_unless_probe_reject_exactly_when_the_probe_fails(agent):
    """The conditional marker rejects a probe-failing payload and spares a probe-passing one."""
    from agentseam.adapters._probes import OBSERVED_MARKERS, PROBES

    mod = adapters.get(agent)
    payload = _sample_payload(agent)
    for probe, markers in VENDOR_CONFIG[agent]["claims"].get("reject_markers_unless_probe", {}).items():
        stripped = {k: v for k, v in payload.items() if k not in OBSERVED_MARKERS}
        assert not PROBES[probe](stripped), "%s: sample still passes %s once stripped" % (agent, probe)
        for marker in markers:
            mutated = dict(stripped, **{marker: "probe-value"})
            assert not mod.claims(mutated), "%s: %r did not reject a probe-failing payload" % (agent, marker)
            mutated[OBSERVED_MARKERS[0]] = "/t.jsonl"
            assert mod.claims(mutated), "%s: %r rejected a probe-passing payload" % (agent, marker)


@pytest.mark.parametrize("agent", MARKER_AGENTS)
def test_accept_when_all_is_a_real_compound(agent):
    """All listed keys present claims the event without a marker; any one missing does not."""
    mod = adapters.get(agent)
    for event_name, required in VENDOR_CONFIG[agent]["claims"].get("accept_when_all", {}).items():
        full = dict({key: "x" for key in required}, hook_event_name=event_name)
        assert mod.claims(full), "%s: the %s compound was not claimed" % (agent, event_name)
        for key in required:
            partial = {k: v for k, v in full.items() if k != key}
            assert not mod.claims(partial), "%s: %s claimed without %r" % (agent, event_name, key)


@pytest.mark.parametrize("agent", MARKER_AGENTS)
def test_client_types_bound_claims(agent):
    """Every listed value is accepted; a value outside the list is rejected."""
    client_types = VENDOR_CONFIG[agent]["claims"].get("client_types")
    if not client_types:
        return
    mod = adapters.get(agent)
    payload = _sample_payload(agent)
    for value in client_types:
        if value is None:
            mutated = {k: v for k, v in payload.items() if k != "client_type"}
        else:
            mutated = dict(payload, client_type=value)
        assert mod.claims(mutated), "%s: declared client_type %r was rejected" % (agent, value)
    mutated = dict(payload, client_type="a-vendor-that-does-not-exist")
    assert not mod.claims(mutated), "%s: an undeclared client_type was accepted" % agent
