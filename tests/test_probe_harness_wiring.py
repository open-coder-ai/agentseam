"""The registry as a probe driver, and conformance over the committed recordings."""

from __future__ import annotations

import json

import pytest

from agentseam import conformance, harness, recordings
from agentseam.contract import PRE_TOOL
from agentseam.probe import conformance_report, recorded_driver


class TestDriverFromTheRegistry:
    def test_the_template_carries_the_probe_s_prompt_slot_unquoted(self):
        """drive_real substitutes an already-quoted JSON string, so the slot must be bare."""
        command = harness.driver_command("claude_code")
        assert harness.DRIVER_PROMPT_SLOT in command
        assert "'%s'" % harness.DRIVER_PROMPT_SLOT not in command
        assert '"%s"' % harness.DRIVER_PROMPT_SLOT not in command

    def test_the_slot_survives_the_substitution_drive_real_performs(self):
        """The end-to-end contract, exercised rather than assumed."""
        command = harness.driver_command("claude_code")
        filled = command.replace(harness.DRIVER_PROMPT_SLOT, json.dumps("do the thing"))
        assert '"do the thing"' in filled
        assert harness.DRIVER_PROMPT_SLOT not in filled

    def test_the_model_flag_lands_in_the_template_where_the_vendor_wants_it(self):
        assert harness.driver_command("codex_cli", model="gpt-5").startswith("codex exec -m gpt-5")

    def test_an_unrecorded_agent_refuses_instead_of_yielding_an_empty_command(self):
        with pytest.raises(harness.NoHarnessError):
            harness.driver_command("windsurf")

    def test_resolve_driver_expands_the_token_into_a_real_command(self):
        """Expanded, not carried: everything downstream must see a live driver, which it is."""
        resolved = recorded_driver.resolve_driver("claude_code", recorded_driver.HARNESS_DRIVER, event="stop")
        assert resolved.startswith("claude ")
        assert resolved not in recorded_driver.NON_LIVE_DRIVERS

    def test_a_harness_driven_run_is_allowed_to_record(self):
        """It really ran an agent, so --record must not refuse it."""
        resolved = recorded_driver.resolve_driver("claude_code", recorded_driver.HARNESS_DRIVER, event="stop")
        assert resolved not in recorded_driver.NON_LIVE_DRIVERS

    def test_the_default_resolution_order_is_unchanged_by_the_new_token(self, monkeypatch):
        """Opt-in by name: whether a run counts as evidence must not shift under anyone.

        The recorded/reference split is stubbed, because which gates are recorded is evidence
        that grows; the order itself is what must not move.
        """
        monkeypatch.setattr(recorded_driver, "has_recording", lambda agent, event, version=None: event == PRE_TOOL)
        assert recorded_driver.resolve_driver("claude_code", None, event=PRE_TOOL) == recorded_driver.DRIVER_NAME
        assert recorded_driver.resolve_driver("claude_code", None, event="stop") == "reference"
        assert recorded_driver.resolve_driver("claude_code", "my-cli {prompt}", event="stop") == "my-cli {prompt}"


class TestConformanceOverRecordings:
    def test_one_recorded_agent_reads_undecidable_everywhere(self):
        """Today's honest answer: one vendor cannot differ from anything."""
        rows = conformance_report.compare(PRE_TOOL)
        assert rows
        assert {r["result"]["call"] for r in rows} == {conformance.UNDECIDABLE}

    def test_no_seam_gap_is_reported_on_the_committed_recordings(self):
        assert conformance_report.gaps() == []

    def test_render_exits_zero_with_nothing_to_compare(self, capsys):
        assert conformance_report.render() == 0
        assert "a comparison needs two" in capsys.readouterr().out

    def test_only_gates_that_were_actually_recorded_are_compared(self):
        """A recording of one gate says nothing about another."""
        recorded = conformance_report.events_recorded()
        assert PRE_TOOL in recorded
        # Whatever the corpus covers, a gate outside it compares to nothing at all.
        assert conformance_report.compare("no-such-gate") == []
        for event in recorded:
            assert conformance_report.compare(event)

    def test_a_second_agent_agreeing_produces_agreement(self, monkeypatch):
        """The mechanism has to work when a second recording lands, not just say undecidable."""
        self._with_twin(monkeypatch, differ=False)
        rows = {r["trial"]: r["result"]["call"] for r in conformance_report.compare(PRE_TOOL)}
        assert rows
        assert set(rows.values()) == {conformance.AGREED}

    def test_a_second_agent_disagreeing_is_a_seam_gap_and_fails_the_gate(self, monkeypatch, capsys):
        """The finding this whole module exists to surface."""
        self._with_twin(monkeypatch, differ=True)
        found = conformance_report.gaps(PRE_TOOL)
        assert found
        assert conformance_report.render(PRE_TOOL) == 1
        assert "seam gap" in capsys.readouterr().out

    @staticmethod
    def _with_twin(monkeypatch, *, differ):
        """Add `cursor` as a second recorded agent, optionally measuring the opposite.

        cursor is used because the matrix records it as able to block at pre_tool, which is what
        makes a disagreement a seam gap rather than an excused vendor limit.
        """
        real = conformance_report._measured

        def measured(agent, trial, event):
            if agent == "cursor":
                value = real("claude_code", trial, event)
                if differ and isinstance(value, bool):
                    return not value
                return value
            return real(agent, trial, event)

        monkeypatch.setattr(recordings, "agents", lambda: ["claude_code", "cursor"])
        monkeypatch.setattr(conformance_report, "_measured", measured)
