"""Value-based detection (org-plan plan/one-oh-gaps.md D1): vendor-doc payloads and the golden pins."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentseam import adapters  # noqa: E402
from agentseam.adapters import vscode_copilot  # noqa: E402
from agentseam.adapters._probes import PROBES  # noqa: E402

FIXTURES = json.loads((ROOT / "tests" / "fixtures" / "detection" / "value_detection.json").read_text(encoding="utf-8"))
GOLDEN_DIR = ROOT / "tests" / "fixtures" / "golden"
CASES = FIXTURES["vendor_doc_payloads"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_a_vendor_doc_payload_detects_as_its_vendor_or_as_no_agent(case):
    """Never as claude_code, or as any agent but its own: an adapterless vendor detects as None."""
    assert adapters.detect(case["payload"]) == case["expect"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_every_vendor_doc_payload_cites_its_source(case):
    """Each fixture names the page it was copied from, the vendor version, and the read date."""
    assert case["source"]["url"].startswith("https://")
    assert case["source"]["version"]
    assert case["source"]["read"] == "2026-10-11"


def test_grok_build_parses_to_the_event_and_tool_it_names():
    """Detected as grok is only honest if grok's own parse reads the newer envelope."""
    case = next(c for c in CASES if c["name"] == "grok_build_pre_tool_use")
    event = adapters.get("grok").parse(case["payload"])
    assert event.event == case["expect_event"]
    assert event.tool == "run_terminal_command"
    assert event.command == "npm test"


@pytest.mark.parametrize("agent", sorted(FIXTURES["golden_detection"]))
def test_golden_fixtures_detect_exactly_as_before_d1(agent):
    """The hard rule: no existing golden fixture changes its detected agent."""
    golden = json.loads((GOLDEN_DIR / ("%s.json" % agent)).read_text(encoding="utf-8"))
    got = {event: adapters.detect(entry["payload"]) for event, entry in sorted(golden["events"].items())}
    assert got == FIXTURES["golden_detection"][agent]


def test_every_golden_fixture_is_pinned():
    """A new golden fixture gets a detection pin too."""
    assert set(FIXTURES["golden_detection"]) == {p.stem for p in GOLDEN_DIR.glob("*.json")}


@pytest.mark.parametrize(
    ("snake", "pascal", "twin"),
    [
        ("pre_tool_use", "PreToolUse", True),
        ("stop", "Stop", True),
        ("preToolUse", "PreToolUse", False),
        ("PreToolUse", "PreToolUse", False),
        ({"a": 1}, "PreToolUse", False),
        (None, "PreToolUse", False),
        ("pre_tool_use", None, False),
    ],
)
def test_vscode_copilot_and_the_grok_probe_agree_on_the_snake_case_twin(snake, pascal, twin):
    """vscode_copilot keeps its own copy (the dialect bundle carries no probe module); the two must agree."""
    raw = {k: v for k, v in (("hookEventName", snake), ("hook_event_name", pascal)) if v is not None}
    assert vscode_copilot._is_grok_build(raw) is twin
    if twin:
        assert PROBES["event_keys_agree"](raw)


@pytest.mark.parametrize(
    ("tool_name", "foreign"),
    [("mcp_postgres_query", True), ("mcp__postgres__query", False), ("Bash", False), ("mcp", False), (7, False)],
)
def test_only_the_single_underscore_mcp_spelling_is_foreign(tool_name, foreign):
    """Claude Code's own mcp__server__tool spelling must never trip the Kiro probe."""
    assert PROBES["names_a_single_underscore_mcp_tool"]({"tool_name": tool_name}) is foreign
