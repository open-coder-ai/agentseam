"""Cross-adapter dispatch: detection, degradation, the one-handler promise."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import (  # noqa: E402
    CC_BASH,
    CC_EDIT,
    CC_MULTI,
    CC_POST,
    CC_WRITE,
    CU_EDIT,
    CU_SHELL,
    CX_SHELL,
    CX_WRITE,
    GM_AFTER,
    GM_REPLACE,
    GM_SHELL,
    GM_WRITE,
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
    }
    ambiguous = {}
    for label, raw in fixtures.items():
        claimants = [name for name, mod in A.adapters.ADAPTERS.items() if mod.claims(raw)]
        if len(claimants) != 1:
            ambiguous[label] = claimants
    assert not ambiguous, "payloads claimed by != 1 adapter: %s" % ambiguous
