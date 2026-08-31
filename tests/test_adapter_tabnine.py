"""Tabnine adapter: a post-tool gate, and a fail-open mode broad enough to be worth a test."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

from scenarios import SCENARIOS  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def _at(event, **over):
    return dict(SCENARIOS["tabnine"][event], **over)


def test_its_gating_events_resolve_to_it_rather_than_being_swallowed():
    """This used to be ambiguous with Gemini, and the ambiguity was not survivable."""
    for event in (A.PRE_TOOL, A.PROMPT_SUBMIT, A.STOP):
        raw = _at(event)
        claimants = sorted(n for n, m in A.adapters.ADAPTERS.items() if m.claims(raw))
        assert claimants == ["tabnine"], "%s claimed by %s" % (event, claimants)
        assert A.adapters.detect(raw) == "tabnine"

    text, _code, ev, _d = A.handle(_at(A.PRE_TOOL), lambda e: Decision.deny("no"))
    assert ev.agent == "tabnine" and "deny" in text, "the deny must survive auto-detection: %r" % text


def test_the_marker_is_required_to_claim():
    without = {k: v for k, v in _at(A.PRE_TOOL).items() if k != "timestamp"}
    assert not A.adapters.get("tabnine").claims(without)


def test_after_tool_can_block_which_most_agents_cannot():
    """Tabnine lets a hook force a retry after execution; elsewhere that is observation only."""
    assert A.can_block("tabnine", A.POST_TOOL)
    body = json.loads(A.handle(_at(A.POST_TOOL), lambda e: Decision.deny("bad output"), agent="tabnine")[0])
    assert body == {"decision": "deny", "reason": "bad output"}


def test_a_non_blocking_event_stays_silent():
    """Stray stdout breaks Tabnine's parsing, and a broken parse is treated as allow -- so"""
    text, code, _e, _d = A.handle(_at(A.SESSION_START), lambda e: Decision.deny("no"), agent="tabnine")
    assert (text, code) == ("", 0)


def test_respond_answers_a_hand_built_event_not_just_a_parsed_one():
    """respond() is public adapter API -- a consumer replaying a captured event or building"""
    from agentseam.contract import Event

    mod = A.adapters.get("tabnine")
    hand_built = Event("tabnine", A.PRE_TOOL, raw=None)
    text, code = mod.respond(Decision.deny("real command"), hand_built)
    assert json.loads(text) == {"decision": "deny", "reason": "real command"}
    assert code == 0

    unknown = Event("tabnine", A.UNKNOWN, raw=None)
    assert mod.respond(Decision.deny("x"), unknown) == ("", 0)


def test_ask_and_rewrite_both_deny_and_name_the_real_cause():
    ask = json.loads(A.handle(_at(A.PRE_TOOL), lambda e: Decision.ask("check first"), agent="tabnine")[0])
    assert ask["decision"] == "deny" and "cannot prompt" in ask["reason"]

    rewrite = json.loads(
        A.handle(_at(A.PRE_TOOL), lambda e: Decision.rewrite({"content": "x"}, "redact"), agent="tabnine")[0]
    )
    assert rewrite["decision"] == "deny"
    assert "redact" in rewrite["reason"] and "cannot modify" in rewrite["reason"]


def test_no_rewrite_is_claimed_even_though_the_vendor_advertises_one():
    """The overview says "rewrite tool arguments"; the field carrying it was not in the"""
    assert not A.can_rewrite("tabnine", A.PRE_TOOL)
    assert "advertised" in A.MATRIX["tabnine"]["notes"]


def test_the_notes_record_how_broadly_it_fails_open():
    """Not pedantry: stdout that is not valid JSON is treated as a message and the action is"""
    notes = A.MATRIX["tabnine"]["notes"]
    assert "ALLOWED" in notes
    assert A.enforcement_level("tabnine", A.PRE_TOOL) == "best-effort"


def test_hook_config_uses_tabnines_own_settings_file():
    mod = A.adapters.get("tabnine")
    assert mod.CONFIG_PATH == ".tabnine/agent/settings.json"
    config = mod.hook_config([A.PRE_TOOL], "guard.py")
    assert config["hooks"]["BeforeTool"][0]["hooks"][0]["command"] == "guard.py"
