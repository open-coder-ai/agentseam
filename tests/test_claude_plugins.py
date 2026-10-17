"""CC-2: each vendor entry records whether its agent loads Claude Code plugins, from CC-1 only."""

from __future__ import annotations

import copy
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from validate_vendor_config import validate  # noqa: E402

from agentseam.vendor_config import SCHEMA, VENDOR_CONFIG, loads_claude_plugins  # noqa: E402

FIELD = "loads_claude_plugins"
WITNESS_FILE = "witness/results/witness-grok-claude-plugin-2026-10-17.md"

#: (loads, hooks, deny_reply) per agent, as org-plan discovery/2026-10-17-claude-plugin-compat.md records them.
DISCOVERY_ROWS = {
    "antigravity": ("no", "n/a", "n/a"),
    "claude_code": ("yes", "yes", "yes"),
    "cline": ("no", "n/a", "n/a"),
    "codex_cli": ("yes", "yes", "yes"),
    "cursor": ("unknown", "unknown", "unknown"),
    "devin": ("yes", "unknown", "partial"),
    "factory_droid": ("yes", "yes", "yes"),
    "gemini_cli": ("no", "n/a", "n/a"),
    "goose": ("partial", "yes", "partial"),
    "grok": ("yes", "yes", "yes"),
    "junie": ("yes", "yes", "partial"),
    "kimi_code": ("no", "n/a", "n/a"),
    "mistral_vibe": ("yes", "unknown", "unknown"),
    "openhands": ("yes", "yes", "partial"),
    "tabnine": ("unknown", "unknown", "unknown"),
    "vscode_copilot": ("yes", "yes", "yes"),
    "windsurf": ("unknown", "unknown", "unknown"),
}


def test_each_entry_records_the_discovery_row():
    assert set(DISCOVERY_ROWS) == set(VENDOR_CONFIG)
    for agent, (loads, hooks, deny_reply) in DISCOVERY_ROWS.items():
        row = VENDOR_CONFIG[agent][FIELD]
        assert (row["loads"], row["hooks"], row["deny_reply"]) == (loads, hooks, deny_reply), agent
        assert "discovery/2026-10-17-claude-plugin-compat.md" in row["source"], agent
        record = VENDOR_CONFIG[agent]["evidence"][FIELD]
        assert record["basis"] in ("vendor-docs", "vendor-source"), agent
        assert record["date"] == "2026-10-17", agent


def test_grok_carries_the_witness_and_no_other_agent_does():
    witnessed = {agent for agent, entry in VENDOR_CONFIG.items() if "witnessed" in entry[FIELD]}
    assert witnessed == {"grok"}
    note = VENDOR_CONFIG["grok"][FIELD]["witnessed"]
    for needle in ("guard", "gate", "refus", "Grok Build 1.0.62", "2026-10-17", WITNESS_FILE, "25b9d9d"):
        assert needle in note, needle
    record = VENDOR_CONFIG["grok"]["evidence"][FIELD]
    assert record["basis"] == "vendor-source"
    assert record["test"].endswith("::test_grok_carries_the_witness_and_no_other_agent_does")


def test_a_no_or_unknown_load_never_reports_a_hook_or_deny_verdict():
    implied = {"no": "n/a", "unknown": "unknown"}
    for agent, entry in VENDOR_CONFIG.items():
        row = entry[FIELD]
        if row["loads"] in implied:
            assert (row["hooks"], row["deny_reply"]) == (implied[row["loads"]],) * 2, agent


def test_vscode_copilot_also_records_the_copilot_cli_row():
    row = VENDOR_CONFIG["vscode_copilot"][FIELD]
    for needle in (
        "Copilot CLI",
        "copilot plugin install",
        ".claude-plugin/plugin.json",
        "nested hookSpecificOutput unknown",
    ):
        assert needle in row["notes"], needle
    assert "github/docs@dae83f7d" in row["source"]


def test_the_field_travels_with_its_own_evidence():
    for agent, entry in VENDOR_CONFIG.items():
        assert (FIELD in entry) == (FIELD in entry["evidence"]), agent


def test_the_accessor_returns_the_recorded_row_and_none_where_unrecorded():
    assert loads_claude_plugins("grok") == VENDOR_CONFIG["grok"][FIELD]
    assert loads_claude_plugins("goose")["loads"] == "partial"
    assert loads_claude_plugins("copilot") is None  # a matrix row with no vendor entry
    assert loads_claude_plugins("no_such_agent") is None


def test_schema_rejects_a_verdict_outside_the_closed_vocabulary():
    mutated = copy.deepcopy(dict(VENDOR_CONFIG["cursor"]))
    mutated[FIELD] = dict(mutated[FIELD], loads="probably")
    assert validate(SCHEMA, mutated)


def test_schema_rejects_an_unknown_key_in_the_field():
    mutated = copy.deepcopy(dict(VENDOR_CONFIG["grok"]))
    mutated[FIELD] = dict(mutated[FIELD], tested="yes")
    assert validate(SCHEMA, mutated)


def test_no_adapter_reads_the_field():
    adapters_dir = ROOT / "src" / "agentseam" / "adapters"
    for path in adapters_dir.glob("*.py"):
        assert FIELD not in path.read_text(encoding="utf-8"), path.name
