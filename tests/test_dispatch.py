"""Cross-adapter dispatch: detection, degradation, the one-handler promise."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import (
    AG_POST_TOOL,
    AG_PRE_TOOL,
    AG_STOP,
    AG_WRITE,
    CC_BASH,
    CC_EDIT,
    CC_MULTI,
    CC_POST,
    CC_WRITE,
    CU_EDIT,
    CU_PRE_TOOL,
    CU_READ,
    CU_SHELL,
    CU_SUBMIT,
    CX_SHELL,
    CX_WRITE,
    DV_PERMISSION,
    DV_PRE_TOOL,
    DV_PROMPT,
    DV_WRITE,  # noqa: E402
    GK_POST,
    GK_SHELL,
    GK_WRITE,
    GM_AFTER,
    GM_REPLACE,
    GM_SHELL,
    GM_WRITE,
    KM_NOTIFY,
    KM_POST,
    KM_SHELL,
    KM_WRITE,
    VS_MEM_CREATE,
    VS_MEM_REPLACE,
    VS_MEM_VIEW,
)

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def allow_all(_e):
    return Decision.allow()


def deny_all(_e):
    return Decision.deny("test-deny")


# ------------------------------------------------------------------ dispatch
def test_detect_never_guesses_between_agents():
    for raw in (CC_WRITE, CU_SHELL, CU_EDIT, VS_MEM_CREATE):
        assert A.adapters.detect(raw) is not None


def test_unknown_payload_allows_silently():
    text, code, event, decision = A.handle({"totally": "unknown"}, deny_all)
    assert (text, code, event) == ("", 0, None) and decision.outcome == A.ALLOW


def test_one_handler_runs_on_every_agent():
    """The core promise: identical handler, correct dialect everywhere."""

    def handler(e):
        return Decision.deny("secret") if "SECRET" in (e.content or "") else Decision.allow()

    outcomes = {}
    for raw in (CC_WRITE, VS_MEM_CREATE, CU_EDIT):
        poisoned = json.loads(json.dumps(raw))
        for holder in (poisoned.get("tool_input", {}), poisoned):
            for k in ("content", "file_text", "new_string"):
                if k in holder:
                    holder[k] = "SECRET"
        if "edits" in poisoned:
            poisoned["edits"] = [{"new_string": "SECRET"}]
        _t, _c, event, decision = A.handle(poisoned, handler)
        outcomes[event.agent] = decision.outcome
    assert outcomes == {"claude_code": "deny", "vscode_copilot": "deny", "cursor": "deny"}


def test_no_two_adapters_claim_the_same_payload():
    """Ambiguous detection silently allows, which is the worst possible failure.

    Codex and VS Code Copilot both use camelCase event names, so this is a live
    hazard rather than a theoretical one; every fixture is checked against every
    adapter so a future adapter cannot quietly widen its claim.
    """
    fixtures = {
        "CC_WRITE": CC_WRITE,
        "CC_EDIT": CC_EDIT,
        "CC_MULTI": CC_MULTI,
        "CC_BASH": CC_BASH,
        "CC_POST": CC_POST,
        "CU_SHELL": CU_SHELL,
        "CU_EDIT": CU_EDIT,
        "VS_MEM_CREATE": VS_MEM_CREATE,
        "VS_MEM_REPLACE": VS_MEM_REPLACE,
        "VS_MEM_VIEW": VS_MEM_VIEW,
        "GM_WRITE": GM_WRITE,
        "GM_REPLACE": GM_REPLACE,
        "GM_SHELL": GM_SHELL,
        "GM_AFTER": GM_AFTER,
        "CX_WRITE": CX_WRITE,
        "CX_SHELL": CX_SHELL,
        "CU_PRE_TOOL": CU_PRE_TOOL,
        "CU_READ": CU_READ,
        "CU_SUBMIT": CU_SUBMIT,
        "DV_PRE_TOOL": DV_PRE_TOOL,
        "DV_WRITE": DV_WRITE,
        "DV_PROMPT": DV_PROMPT,
        "DV_PERMISSION": DV_PERMISSION,
        "GK_SHELL": GK_SHELL,
        "GK_WRITE": GK_WRITE,
        "GK_POST": GK_POST,
        "AG_PRE_TOOL": AG_PRE_TOOL,
        "AG_WRITE": AG_WRITE,
        "AG_POST_TOOL": AG_POST_TOOL,
        "AG_STOP": AG_STOP,
        "KM_SHELL": KM_SHELL,
        "KM_WRITE": KM_WRITE,
        "KM_POST": KM_POST,
        "KM_NOTIFY": KM_NOTIFY,
    }
    ambiguous = {}
    for label, raw in fixtures.items():
        claimants = [name for name, mod in A.adapters.ADAPTERS.items() if mod.claims(raw)]
        if len(claimants) != 1:
            ambiguous[label] = claimants
    assert not ambiguous, "payloads claimed by != 1 adapter: %s" % ambiguous


def test_degradation_records_its_origin():
    """A twice-degraded decision must still report the original cause.

    rewrite -> ask (no rewrite support) -> block (no ask support) is a real chain on
    Windsurf. Without recording the origin, the user is told confirmation was
    unavailable for something that was never a confirmation request.
    """
    from payloads import WS_COMMAND

    event = A.adapters.get("windsurf").parse(WS_COMMAND)
    degraded = A.degrade(Decision.rewrite({"command": "true"}, "redact the token"), event)
    assert degraded.outcome == A.ASK
    assert degraded.evidence["degraded_from"] == A.REWRITE

    text, code, _, _ = A.handle(WS_COMMAND, lambda e: Decision.rewrite({"command": "true"}, "redact the token"))
    assert code == 2
    assert "cannot rewrite" in text and "redact the token" in text


def test_plain_ask_is_not_reported_as_a_rewrite():
    from payloads import WS_COMMAND

    text, code, _, _ = A.handle(WS_COMMAND, lambda e: Decision.ask("needs review"))
    assert code == 2
    assert "cannot prompt for confirmation" in text


def test_a_payload_naming_another_client_is_not_claimed_by_lookalikes():
    """SessionStart is spelled identically by Claude Code, Gemini CLI, Devin and Kimi Code.

    Only Kimi carries proof of which it is, so the general rule is that a positive
    self-identification beats a shared event name. Without it, both lookalikes claim the
    payload, detection goes ambiguous, and the dispatcher allows what it was gating.
    """
    kimi_session_start = {"hook_event_name": "SessionStart", "client_type": "kimi_code_cli", "session_id": "s"}
    assert A.adapters.detect(kimi_session_start) == "kimi_code"

    # Strip the proof and it is genuinely ambiguous again -- which is the honest answer.
    anonymous = {k: v for k, v in kimi_session_start.items() if k != "client_type"}
    assert A.adapters.detect(anonymous) is None
