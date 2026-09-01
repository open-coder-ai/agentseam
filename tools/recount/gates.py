"""Executed against the D1 golden fixture: which grammar each gate speaks, and what it honours.

Every gate's `grammar`/`honours_escalate`/`honours_transform` is read off `tests/fixtures/
golden/<agent>.json` -- the frozen (payload -> stdout, exit) truth wave D1 captured by running
the real dispatcher (`agentseam.handle`, `dispatch.degrade()` included). That is deliberate: a
claim like "this gate honours escalate" is only true operationally if the END-TO-END pipeline
(matrix-aware degrade + adapter dialect) produces a distinguishable response, which matches
this project's own definition of "tested" (org-plan plan/agentseam-project.md): "an automated
check exercises the claim against OUR RUNTIME". Field names follow the post-W35 ACS
vocabulary (`contract.py`: `escalate`/`transform`, not the pre-ACS `ask`/`rewrite`) -- the
local `ask`/`rewrite` names below are D1's own golden-fixture outcome labels, untouched here.
"""

from __future__ import annotations

import json
import os

from agentseam.allow_semantics import ALLOW_SEMANTICS

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FIXTURE_DIR = os.path.join(ROOT, "tests", "fixtures", "golden")


def _load_fixture(agent):
    with open(os.path.join(FIXTURE_DIR, "%s.json" % agent), encoding="utf-8") as fh:
        return json.load(fh)


def _classify_grammar(stdout, exit_code):
    if exit_code != 0:
        return "G5"
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        body = json.loads(text)
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    if "permission" in body or "continue" in body:
        return "G4"
    if "hookSpecificOutput" in body:
        inner = body["hookSpecificOutput"]
        if not isinstance(inner, dict):
            return None
        if "permissionDecision" in inner:
            return "G2"
        if "decision" in inner or "tool_input" in inner or "updatedInput" in inner:
            return "G3"
        return None  # e.g. a bare additionalContext note -- observational, not a verdict
    if "decision" in body:
        return "G1"
    return None


def _classify_transform_grammar(stdout):
    text = (stdout or "").strip()
    if not text:
        return None
    try:
        body = json.loads(text)
    except ValueError:
        return None
    if not isinstance(body, dict):
        return None
    inner = body.get("hookSpecificOutput")
    if isinstance(inner, dict) and "tool_input" in inner:
        return "hook_specific_tool_input"
    if isinstance(inner, dict) and "updatedInput" in inner and inner.get("updatedInput") is not None:
        return "hook_specific_updated_input"
    if "updatedInput" in body and body.get("updatedInput") is not None:
        return "top_level_updated_input"
    if "updated_input" in body:
        return "permission_updated_input"
    return None


def _words(stdout):
    """Every decision-word value in this response, at any depth (test_decision_vocabulary.py)."""
    text = (stdout or "").strip()
    if not text:
        return set()
    try:
        body = json.loads(text)
    except ValueError:
        return set()
    found = set()
    stack = [body]
    while stack:
        node = stack.pop()
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("decision", "permission", "permissionDecision") and isinstance(value, str):
                    found.add(value)
                elif isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(node, list):
            stack.extend(node)
    return found


def _classify_outcomes(deny, ask, rewrite):
    grammar = _classify_grammar(deny["stdout"], deny["exit"])
    if grammar is None:
        return None
    honours_escalate = ask != deny and bool(_words(ask["stdout"]) - _words(deny["stdout"]))
    honours_transform = rewrite != deny and _classify_transform_grammar(rewrite["stdout"]) is not None
    return {"grammar": grammar, "honours_escalate": honours_escalate, "honours_transform": honours_transform}


#: Cursor names FIVE distinct wire events for canonical pre_tool (cursor.py:51-57's
#: `_PERMISSION_GATES`), each with its own honours_escalate -- but `REVERSE_EVENT_MAP` picks only
#: "preToolUse" to emit, so D1's one-scenario-per-canonical-event golden fixture never
#: exercises the other four. Recounted here by executing the real dispatcher
#: (`agentseam.handle`, degrade() included) against the SAME frozen pre_tool payload with
#: only `hook_event_name` swapped -- not a second, hand-guessed source of truth.
_EXTRA_GATE_NAMES = {
    "cursor": ("beforeShellExecution", "beforeMCPExecution", "beforeReadFile", "beforeTabFileRead"),
    "devin": ("PermissionRequest",),
    "junie": ("PermissionRequest",),
    # windsurf's REVERSE_EVENT_MAP emits pre_run_command for pre_tool, so D1's fixture
    # never exercises its second, equally blocking pre_tool wire name.
    "windsurf": ("pre_mcp_tool_use",),
}


def _extra_gates(agent, canonical_source_event):
    names = _EXTRA_GATE_NAMES.get(agent)
    if not names:
        return {}
    from capture_fixtures import OUTCOMES

    import agentseam as A

    base_payload = _load_fixture(agent)["events"][canonical_source_event]["payload"]
    factories = dict(OUTCOMES)
    out = {}
    for name in names:
        payload = dict(base_payload, hook_event_name=name)

        def _speak(outcome):
            text, code, _e, _d = A.handle(payload, lambda _e, f=factories[outcome]: f(), agent=agent)
            return {"stdout": text, "exit": code}

        classified = _classify_outcomes(_speak("deny"), _speak("ask"), _speak("rewrite"))
        if classified is not None:
            out[name] = classified
    return out


def _gates(agent, mod):
    """Per vendor-event gate table, replayed straight out of the D1 golden fixture."""
    fixture = _load_fixture(agent)
    reverse = getattr(mod, "REVERSE_EVENT_MAP", {})
    gates = {}
    transform_grammar = None
    empty_object = []
    for canonical_event, entry in sorted(fixture["events"].items()):
        vendor_name = reverse.get(canonical_event, canonical_event)
        if all(o == {"stdout": "{}", "exit": 0} for o in entry["outcomes"].values()):
            empty_object.append(vendor_name)  # a fixed acknowledgement, not a verdict
            continue
        deny = entry["outcomes"]["deny"]
        ask = entry["outcomes"]["ask"]
        rewrite = entry["outcomes"]["rewrite"]
        classified = _classify_outcomes(deny, ask, rewrite)
        if classified is None:
            continue  # not a gate: this canonical event never speaks a verdict
        if classified["honours_transform"]:
            transform_grammar = _classify_transform_grammar(rewrite["stdout"])
        gates[vendor_name] = classified
        if canonical_event == "pre_tool":
            gates.update(_extra_gates(agent, canonical_event))
    return gates, transform_grammar, empty_object


def _vocabulary_basis(agent):
    """Tabnine's DECISION_VOCABULARY rests on nothing recorded (allow_semantics.py's own
    comment: "the only such entry here"); every other vendor's is cross-checked against a
    read source. Re-homes test_the_unverified_vocabulary_is_still_only_tabnine's intent
    (dialect-families.md §5) as a fact about this config rather than a source-file grep."""
    return "unverified" if agent == "tabnine" else "verified"


def verdicts(agent, mod):
    from .tables import verdict_dialect

    gates, transform_grammar, empty_object = _gates(agent, mod)
    out = {
        "vocabulary": sorted(mod.DECISION_VOCABULARY),
        "vocabulary_basis": _vocabulary_basis(agent),
        "bare_allow": ALLOW_SEMANTICS[agent][0],
        "answer_events": sorted(gates),
        "gates": gates,
    }
    if transform_grammar:
        out["transform_grammar"] = transform_grammar
    if empty_object:
        out["empty_object_events"] = sorted(empty_object)
    out.update(verdict_dialect(agent))
    return out
