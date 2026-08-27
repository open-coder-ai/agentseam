"""Junie adapter: the strongest gate here, and the config location that makes it weak."""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

import pytest  # noqa: E402
from scenarios import SCENARIOS  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def _pre(**over):
    return dict(SCENARIOS["junie"][A.PRE_TOOL], **over)


def test_project_path_separates_junie_from_claude_code():
    """Junie reuses Claude Code's event AND field names on purpose -- it says so."""
    raw = _pre()
    assert A.adapters.detect(raw) == "junie"
    without = {k: v for k, v in raw.items() if k != "project_path"}
    assert A.adapters.detect(without) == "claude_code"


@pytest.mark.parametrize(
    "decision,expected",
    [
        (lambda: Decision.deny("secret detected"), {"decision": "deny", "reason": "secret detected"}),
        (lambda: Decision.ask("confirm?"), {"decision": "ask", "reason": "confirm?"}),
    ],
)
def test_block_and_ask_are_native(decision, expected):
    text, code, _e, final = A.handle(_pre(), lambda e: decision(), agent="junie")
    assert json.loads(text) == expected
    assert code == 0
    assert final.evidence.get("degraded_from") is None


def test_rewrite_is_native_and_carries_updated_input():
    """No degradation: PreToolUse takes updatedInput, so a rewrite is honoured as asked."""
    text, _c, _e, final = A.handle(
        _pre(), lambda e: Decision.rewrite({"content": "<redacted>"}, "redacting"), agent="junie"
    )
    body = json.loads(text)
    assert body["decision"] == "allow"
    assert body["updatedInput"] == {"content": "<redacted>"}
    assert final.outcome == A.REWRITE, "the dispatcher should not have reduced this"


def test_a_rewrite_without_replacement_input_denies_rather_than_allowing():
    """Emitting `allow` with no updatedInput would let the original through unchanged."""
    body = json.loads(A.handle(_pre(), lambda e: Decision.rewrite(None, "needs redaction"), agent="junie")[0])
    assert body["decision"] == "deny"
    assert "no replacement input" in body["reason"]


def test_permission_request_is_answered_explicitly_because_silence_approves():
    """A hook exiting 0 without a decision approves and skips the dialog the user would
    otherwise have seen, so staying silent there is itself a decision.
    """
    raw = _pre(hook_event_name="PermissionRequest", permission_reason="writes outside project")
    text, code, event, _d = A.handle(raw, lambda e: Decision.allow(), agent="junie")
    assert event.event == A.PRE_TOOL
    assert json.loads(text)["decision"] == "allow"
    assert code == 0
    assert json.loads(A.handle(raw, lambda e: Decision.deny("no"), agent="junie")[0])["decision"] == "deny"


def test_permission_request_is_not_bundled_into_a_pre_tool_install():
    """PermissionRequest approves by default; PreToolUse denies by default. Both map to
    canonical pre_tool, but install('junie', ['pre_tool']) must wire only PreToolUse --
    bundling the two would hand a consumer a second, higher-stakes gate with inverted
    semantics they never asked for. Deliberate, not a coverage gap; documented in the
    module docstring and the matrix note."""
    mod = A.adapters.get("junie")
    config = mod.hook_config([A.PRE_TOOL], "handler.py")
    assert list(config["hooks"]) == ["PreToolUse"]
    assert "PermissionRequest" not in config["hooks"]


def test_stop_speaks_retry_not_permission():
    raw = dict(SCENARIOS["junie"][A.STOP])
    body = json.loads(A.handle(raw, lambda e: Decision.deny("tests still failing"), agent="junie")[0])
    assert body == {"decision": "block", "reason": "tests still failing"}


def test_stop_failure_is_not_mapped_to_tool_failure():
    """It fires on LLM/API failures; the vendor says tool errors are future work."""
    mod = A.adapters.get("junie")
    assert "StopFailure" not in mod.EVENT_MAP
    assert A.TOOL_FAILURE not in A.MATRIX["junie"]["events"]


def test_config_targets_the_user_file_because_project_hooks_are_ignored():
    """A guardrail committed to a repo does not run for a teammate who clones it.

    Junie skips hooks from a repository-controlled config unless it is passed explicitly,
    so writing there would produce a config that silently never fires.
    """
    mod = A.adapters.get("junie")
    assert mod.CONFIG_PATH.startswith("~/")
    assert "IGNORED by default" in A.MATRIX["junie"]["notes"]


def test_junie_fails_open():
    assert A.enforcement_level("junie", A.PRE_TOOL) == "best-effort"
    assert A.can_rewrite("junie", A.PRE_TOOL)
