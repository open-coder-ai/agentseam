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
    """Ambiguous detection silently allows, which is the worst possible failure."""
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
    """A twice-degraded decision must still report the original cause."""
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
    """SessionStart is spelled identically by Claude Code, Gemini CLI, Devin and Kimi Code."""
    kimi_session_start = {"hook_event_name": "SessionStart", "client_type": "kimi_code_cli", "session_id": "s"}
    assert A.adapters.detect(kimi_session_start) == "kimi_code"

    anonymous = {k: v for k, v in kimi_session_start.items() if k != "client_type"}
    assert A.adapters.detect(anonymous) is None


def test_run_survives_a_bom_from_the_platform_locale():
    """A UTF-8 BOM on stdin must not turn every decision into a silent allow."""
    import io

    payload = json.dumps(CC_WRITE).encode("utf-8")
    seen = []

    def handler(event):
        seen.append(event.event)
        return Decision.deny("no")

    stream = io.TextIOWrapper(io.BytesIO(b"\xef\xbb\xbf" + payload), encoding="cp1252")
    out = io.StringIO()
    from agentseam import dispatch as dispatch_mod

    dispatch_mod.run(handler, stdin=stream, stdout=out, exit=False)
    assert seen == ["pre_tool"], "the BOM ate the payload: handler saw %s" % seen
    assert "deny" in out.getvalue(), out.getvalue()


def test_a_non_ascii_reason_does_not_crash_the_gate_on_a_locale_stdout():
    """The output twin of the BOM bug: a policy reason with a non-cp1252 char must not"""
    import io

    class LocaleStdout:
        """stdout whose text layer is cp1252 (raises) but whose buffer is real bytes."""

        def __init__(self):
            self.buffer = io.BytesIO()

        def write(self, s):
            s.encode("cp1252")
            self.buffer.write(s.encode("cp1252"))

        def flush(self):
            pass

    def handler(event):
        return Decision.deny("blocked: 危険 \U0001f6ab")

    from agentseam import dispatch

    out = LocaleStdout()
    payload = {"hook_event_name": "pre_run_command", "toolName": "pre_run_command", "tool_input": {"command": "x"}}
    code = dispatch.run(handler, agent="windsurf", stdin=io.StringIO(json.dumps(payload)), stdout=out, exit=False)
    assert code == 2, "the block's exit code must survive the write, not be pre-empted by a crash"
    assert "危険" in out.buffer.getvalue().decode("utf-8"), "the reason must reach stdout intact"
