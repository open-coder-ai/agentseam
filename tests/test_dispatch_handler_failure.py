"""A handler that cannot decide refuses: exceptions, wrong return types, and a dead stderr."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "examples"))

from payloads import CC_BASH  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def _allow(_event):
    return Decision.allow()


def _boom(_event):
    raise RuntimeError("token=hunter2 leaked from the payload")


def test_a_handler_that_raises_is_refused_in_dialect_not_crashed_through():
    """A door that cannot decide refuses. Letting the exception escape exits the hook with 1

    and a traceback, which every host reads as a non-blocking error: the crash trial in
    data/recordings witnessed Claude Code run the tool regardless (observed.runs == 1)."""
    from agentseam import dispatch

    text, code, event, decision = A.handle(CC_BASH, _boom)
    assert event is not None and event.event == A.PRE_TOOL
    assert decision.outcome == A.DENY
    assert json.loads(text)["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert code == 0
    assert "RuntimeError" in decision.reason
    assert decision.evidence[dispatch.HANDLER_ERROR].startswith("RuntimeError: token=hunter2")
    assert "Traceback" in decision.evidence[dispatch.HANDLER_TRACEBACK]


def test_the_refusal_names_the_failure_class_but_never_its_message():
    """An exception message may quote the payload the policy was inspecting -- a secret it
    caught, a path -- and the reason goes back to the agent. Only the class travels."""
    text, _code, _event, _decision = A.handle(CC_BASH, _boom)
    assert "hunter2" not in text


def test_a_handler_returning_the_wrong_type_is_refused_the_same_way():
    text, _code, _event, decision = A.handle(CC_BASH, lambda _e: "allow")
    assert decision.outcome == A.DENY and "TypeError" in decision.reason
    assert json.loads(text)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_run_refuses_on_stdout_and_puts_the_traceback_on_stderr(capsys):
    import io

    from agentseam import dispatch

    out = io.StringIO()
    code = dispatch.run(_boom, stdin=io.StringIO(json.dumps(CC_BASH)), stdout=out, exit=False)
    assert code == 0 and json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] == "deny"
    err = capsys.readouterr().err
    assert "Traceback" in err and "RuntimeError: token=hunter2" in err, err


def test_a_raising_handler_is_refused_at_every_blocking_gate_of_every_agent():
    """Where the vendor can block, the refusal is the same wire output an explicit deny with
    the same reason produces -- the witnessed path, not an improvised one."""
    from scenarios import SCENARIOS

    for agent, events in sorted(SCENARIOS.items()):
        for event, raw in sorted(events.items()):
            if not A.can_block(agent, event):
                continue
            text, code, _e, decision = A.handle(raw, _boom, agent=agent)
            expected, expected_code, _e2, _d2 = A.handle(
                raw, lambda _e, r=decision.reason: Decision.deny(r), agent=agent
            )
            assert (text, code) == (expected, expected_code), "%s/%s" % (agent, event)
            assert text.strip() or code != 0, "%s/%s: a blocking gate was answered with silence" % (agent, event)


def test_run_exits_with_the_blocking_code_when_the_dispatcher_itself_fails(monkeypatch, capsys):
    """Past the handler there is no Event to answer in dialect; the one refusal left is exit 2."""
    import io

    from agentseam import dispatch

    class Broken:
        AGENT = "claude_code"

        @staticmethod
        def parse(_raw):
            raise KeyError("adapter defect")

    monkeypatch.setattr(dispatch.adapters, "get", lambda _name: Broken)
    out = io.StringIO()
    code = dispatch.run(_allow, agent="claude_code", stdin=io.StringIO(json.dumps(CC_BASH)), stdout=out, exit=False)
    assert code == dispatch.DISPATCH_FAILURE_EXIT and out.getvalue() == ""
    assert "adapter defect" in capsys.readouterr().err


def test_a_dead_stderr_never_pre_empts_the_refusal(monkeypatch):
    """The traceback is a courtesy to the operator; the verdict is the contract. stderr may
    be closed (sys.stderr is None), a code page the payload text does not fit, or a dead pipe."""
    import io

    from agentseam import dispatch

    class Dead:
        def write(self, _text):
            raise OSError("nobody is listening")

        def flush(self):
            raise OSError("nobody is listening")

    for stderr in (Dead(), None):
        monkeypatch.setattr(sys, "stderr", stderr)
        out = io.StringIO()
        code = dispatch.run(_boom, stdin=io.StringIO(json.dumps(CC_BASH)), stdout=out, exit=False)
        assert code == 0 and json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_a_handlers_odd_evidence_shape_does_not_trip_the_diagnostic(capsys):
    """`evidence` is the handler's to fill; a list there must not crash run() after the verdict
    was already decided -- that crash would be exit 1, the fail-open exit."""
    import io

    from agentseam import dispatch

    out = io.StringIO()
    handler = lambda _e: Decision.deny("no", evidence=["not", "a", "dict"])  # noqa: E731
    code = dispatch.run(handler, stdin=io.StringIO(json.dumps(CC_BASH)), stdout=out, exit=False)
    assert code == 0 and json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert capsys.readouterr().err == ""
