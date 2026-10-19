"""A payload is never allowed because nobody claimed it (prerelease review, agentseam B1).

Three guarantees, each pinned: the agent an install wires is bound on the hook command and read
back before detection runs; VS Code's `timestamp` envelope yields to every other vendor's own
marks; and a payload no adapter (or more than one) claims is refused out loud wherever a host
would read silence as a verdict, and left silent everywhere else.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "examples"))

from scenarios import SCENARIOS  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import adapters, dispatch  # noqa: E402
from agentseam import install as I  # noqa: E402
from agentseam.adapters import _copilot_claims  # noqa: E402
from agentseam.install_config import bind_agent  # noqa: E402

TIMESTAMP = {"timestamp": "2026-10-19T00:00:00.000Z"}

#: The six payloads the review reproduced B1 on, plus every other vendor's gate payloads.
REVIEWED = ("cursor", "devin", "junie", "kimi_code", "factory_droid", "grok")

#: Vendors whose entry rejects `timestamp` outright, so adding it hands the payload to the
#: vendor whose envelope that key is: Claude Code's to VS Code, Gemini's to Tabnine (the
#: deliberate tie-break on their identical wire). Pinned as the single swap it is, not hidden.
TIMESTAMP_IS_SOMEONE_ELSES = {"claude_code": "vscode_copilot", "gemini_cli": "tabnine"}

GATES = sorted(set(dispatch.VERDICT_EVENTS))
GATE_PAYLOADS = [
    (agent, event) for agent, events in sorted(SCENARIOS.items()) for event in sorted(events) if event in GATES
]


def deny_all(_e):
    return A.Decision.deny("test-deny")


def allow_all(_e):
    return A.Decision.allow()


# --- 1. the envelope yields to a vendor's own marks -------------------------------------------


@pytest.mark.parametrize("agent", REVIEWED)
def test_the_six_reviewed_payloads_plus_timestamp_detect_as_their_own_vendor(agent):
    raw = dict(SCENARIOS[agent][A.PRE_TOOL], **TIMESTAMP)
    assert adapters.detect(raw) == agent, adapters.claimants(raw)


@pytest.mark.parametrize(("agent", "event"), GATE_PAYLOADS)
def test_a_timestamp_key_changes_no_gate_payloads_claimants(agent, event):
    """Every vendor's pre_tool, prompt_submit and stop payload: `timestamp` added, same claimants."""
    raw = SCENARIOS[agent][event]
    before, after = adapters.claimants(raw), adapters.claimants(dict(raw, **TIMESTAMP))
    if agent in TIMESTAMP_IS_SOMEONE_ELSES:
        assert (before, after) == ([agent], [TIMESTAMP_IS_SOMEONE_ELSES[agent]])
    else:
        assert after == before == [agent]


#: Observation-event payloads that were one vendor's alone before `timestamp` is added. Left out:
#: claude_code's and gemini_cli's (their entries reject the key by design, see above) and payloads
#: already shared before (Devin's bare SessionStart carries no mark of its own).
OBSERVATION_PAYLOADS = [
    (agent, event)
    for agent, events in sorted(SCENARIOS.items())
    for event in sorted(events)
    if event not in GATES
    and agent not in TIMESTAMP_IS_SOMEONE_ELSES
    and adapters.claimants(SCENARIOS[agent][event]) == [agent]
]


@pytest.mark.parametrize(("agent", "event"), OBSERVATION_PAYLOADS)
def test_a_timestamp_key_does_not_hand_an_observation_payload_to_tabnine_too(agent, event):
    """tabnine.json accepts `timestamp` alone, so it claimed Codex's, Junie's, Kimi's, Droid's and Devin's
    SessionStart/SessionEnd the moment a timestamp appeared; its reject_markers now carry their marks."""
    raw = SCENARIOS[agent][event]
    assert adapters.claimants(dict(raw, **TIMESTAMP)) == [agent]


def test_vscode_still_claims_every_payload_of_its_own():
    """SessionStart carries `model` (Cursor's marker too), which is why the envelope does not yield to it.
    Tabnine shares that one observation-only payload, as it did before (the generated page says so)."""
    for event, raw in SCENARIOS["vscode_copilot"].items():
        assert adapters.get("vscode_copilot").claims(raw), event
        if event != A.SESSION_START:
            assert adapters.detect(raw) == "vscode_copilot", event


def test_a_claude_shaped_prompt_id_payload_is_still_vs_codes():
    """Claude Code sends prompt_id beside transcript_path; VS Code merges transcript_path into everything."""
    raw = dict(SCENARIOS["vscode_copilot"][A.PRE_TOOL], prompt_id="p-1", transcript_path="/t")
    assert adapters.detect(raw) == "vscode_copilot"


def test_droid_permission_modes_are_the_same_five_everywhere():
    """One list, three copies: the envelope's exclusion, Droid's acceptance, Claude Code's rejection."""
    droid = adapters.get("factory_droid").CONFIG["claims"]["accept_values"]["permission_mode"]
    claude = adapters.get("claude_code").CONFIG["claims"]["reject_values"]["permission_mode"]
    assert list(_copilot_claims.DROID_PERMISSION_MODES) == list(droid) == list(claude)


def test_codex_session_start_is_claimed_by_both_and_dispatch_stays_silent():
    """matrix-notes codex_cli: a real SessionStart (no turn_id) is claude_code's and codex_cli's; detect()
    declines, and at an event that carries no verdict the dispatcher says nothing and exits 0."""
    raw = {
        "hook_event_name": "SessionStart",
        "session_id": "s",
        "transcript_path": "/t",
        "cwd": "/repo",
        "model": "gpt-5-codex",
        "permission_mode": "default",
        "source": "startup",
    }
    assert adapters.claimants(raw) == ["claude_code", "codex_cli"]
    assert adapters.detect(raw) is None
    text, code, event, decision = A.handle(raw, deny_all)
    assert (text, code, event, decision.outcome) == ("", 0, None, A.ALLOW)


# --- 2. an unclaimed payload at a gate is refused out loud ------------------------------------

#: Devin's prompt_id and Junie's project_path on one Claude-shaped PreToolUse: two claimants.
AMBIGUOUS_PRE_TOOL = {
    "hook_event_name": "PreToolUse",
    "session_id": "s",
    "prompt_id": "p-1",
    "project_path": "/repo",
    "tool_name": "Bash",
    "tool_input": {"command": "rm -rf /"},
}

#: Kiro-shaped: claude_code rejects its tool names by value and nothing else claims it.
UNCLAIMED_PRE_TOOL = {"hook_event_name": "PreToolUse", "session_id": "s", "tool_name": "fs_write", "tool_input": {}}


def test_an_ambiguous_gate_payload_is_refused_not_passed():
    assert len(adapters.claimants(AMBIGUOUS_PRE_TOOL)) > 1
    text, code, event, decision = A.handle(AMBIGUOUS_PRE_TOOL, allow_all)
    assert (text, code, event) == ("", dispatch.DISPATCH_FAILURE_EXIT, None)
    assert decision.outcome == A.DENY and decision.reason == dispatch.UNRECOGNIZED
    assert decision.evidence[dispatch.CLAIMANTS] == ["devin", "junie"]


def test_an_unclaimed_gate_payload_is_refused_too():
    assert adapters.claimants(UNCLAIMED_PRE_TOOL) == []
    text, code, event, decision = A.handle(UNCLAIMED_PRE_TOOL, allow_all)
    assert (text, code, event, decision.outcome) == ("", dispatch.DISPATCH_FAILURE_EXIT, None, A.DENY)


@pytest.mark.parametrize("event", [A.PROMPT_SUBMIT, A.STOP])
def test_every_verdict_event_refuses(event):
    name = adapters.get("claude_code").REVERSE_EVENT_MAP[event]
    raw = dict(AMBIGUOUS_PRE_TOOL, hook_event_name=name)
    assert A.handle(raw, allow_all)[1] == dispatch.DISPATCH_FAILURE_EXIT


def test_an_observation_only_event_stays_silent():
    raw = dict(AMBIGUOUS_PRE_TOOL, hook_event_name="SessionStart")
    text, code, _event, decision = A.handle(raw, deny_all)
    assert (text, code, decision.outcome) == ("", 0, A.ALLOW)


def test_a_payload_no_adapter_can_read_stays_silent():
    text, code, event, decision = A.handle({"totally": "unknown"}, deny_all)
    assert (text, code, event, decision.outcome) == ("", 0, None, A.ALLOW)


def test_run_prints_one_line_naming_the_claimants_and_exits_2(capsys):
    stdin = _Stdin(AMBIGUOUS_PRE_TOOL)
    code = A.run(allow_all, stdin=stdin, exit=False)
    out, err = capsys.readouterr()
    assert (code, out) == (dispatch.DISPATCH_FAILURE_EXIT, "")
    assert err.count("\n") == 1 and "devin, junie" in err and "pre_tool" in err


class _Stdin:
    def __init__(self, payload):
        self._text = json.dumps(payload)

    def read(self):
        return self._text


# --- 3. install binds the agent; run() reads it before detect() ------------------------------


def test_bind_agent_appends_the_name_once():
    assert bind_agent("python3 guard.py", "claude_code") == "python3 guard.py claude_code"
    assert bind_agent("python3 guard.py claude_code", "claude_code") == "python3 guard.py claude_code"
    assert bind_agent("python3 guard.py cursor", "claude_code") == "python3 guard.py cursor claude_code"


def test_bound_agent_reads_the_environment_then_the_last_argument():
    assert dispatch.bound_agent(["h.py"], {dispatch.AGENT_ENV: "cursor"}) == "cursor"
    assert dispatch.bound_agent(["h.py", "claude_code"], {}) == "claude_code"
    assert dispatch.bound_agent(["h.py", "--flag", "claude_code"], {}) == "claude_code"
    assert dispatch.bound_agent(["h.py"], {}) is None
    assert dispatch.bound_agent(["h.py", "nobody"], {dispatch.AGENT_ENV: "nobody"}) is None


@pytest.mark.parametrize(("agent", "key"), [("claude_code", "command"), ("cursor", "command")])
def test_install_writes_the_bound_command(agent, key, tmp_path):
    path = I.install(agent, [A.PRE_TOOL], "python3 guard.py", str(tmp_path))
    with open(path, encoding="utf-8") as fh:
        text = fh.read()
    assert '"%s": "python3 guard.py %s"' % (key, agent) in text
    assert I.installed(agent, str(tmp_path), events=[A.PRE_TOOL], command="python3 guard.py")


def test_hook_dir_and_toml_installs_bind_too(tmp_path):
    cline = Path(I.install("cline", [A.PRE_TOOL], "python3 guard.py", str(tmp_path)))
    assert "python3 guard.py cline\n" in next(cline.iterdir()).read_text(encoding="utf-8")
    vibe = Path(I.install("mistral_vibe", [A.PRE_TOOL], "python3 guard.py", str(tmp_path)))
    assert 'command = "python3 guard.py mistral_vibe"' in vibe.read_text(encoding="utf-8")


def test_run_with_a_bound_agent_never_consults_detection(monkeypatch, capsys):
    def no_detection(_raw):
        raise AssertionError("detect() ran on a bound hook")

    monkeypatch.setattr(adapters, "detect", no_detection)
    monkeypatch.setattr(sys, "argv", ["guard.py", "claude_code"])
    code = A.run(deny_all, stdin=_Stdin(AMBIGUOUS_PRE_TOOL), exit=False)
    out = capsys.readouterr().out
    assert code == 0 and json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"


HANDLER = """\
import sys
from agentseam import Decision, run

def handler(event):
    return Decision.deny("bound: %s" % event.agent)

run(handler)
"""


def test_the_installed_command_reaches_the_handler_without_detection(tmp_path):
    """Acceptance: `install claude_code` emits the bound form and a hook run with no detection
    reaches the handler -- on a payload detect() itself refuses."""
    (tmp_path / "guard.py").write_text(HANDLER, encoding="utf-8")
    settings = I.install("claude_code", [A.PRE_TOOL], "%s guard.py" % sys.executable, str(tmp_path))
    with open(settings, encoding="utf-8") as fh:
        command = json.load(fh)["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command.endswith(" guard.py claude_code")
    env = dict(os.environ, PYTHONPATH=os.pathsep.join([str(ROOT / "src"), os.environ.get("PYTHONPATH", "")]))
    proc = subprocess.run(  # noqa: S602 (the shell is the host's, running the line install wrote)
        command,
        shell=True,
        cwd=str(tmp_path),
        input=json.dumps(AMBIGUOUS_PRE_TOOL),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecisionReason"] == "bound: claude_code"
    unbound = subprocess.run(  # noqa: S602
        command.rsplit(" ", 1)[0],
        shell=True,
        cwd=str(tmp_path),
        input=json.dumps(AMBIGUOUS_PRE_TOOL),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert (unbound.returncode, unbound.stdout) == (2, "") and "devin, junie" in unbound.stderr
