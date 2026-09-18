"""experiment_driver.drive_real: the operator's `--driver` template, and the one way it lies.

The registry's own templates are already asserted to carry the prompt slot bare
(test_probe_harness_wiring). Nothing checked the template an operator types, and that is the
one a contributor writes by hand while following docs/coverage-gaps.md.
"""

from __future__ import annotations

import pytest

from agentseam.probe import experiment_driver


@pytest.mark.parametrize("template", ['claude -p "{prompt}"', "claude -p '{prompt}'", 'x --msg "{prompt}" -y'])
def test_a_quoted_prompt_slot_is_refused(template):
    """Quoting the slot ends the operator's quote early and hands `>>` to the shell.

    The trigger the probe asks the agent to run contains `echo ok >> ACTION_RAN`. With the
    quote closed early that redirect is the shell's, so the driver's own chat output is
    appended to the sentinel file, the run counts sentinel lines and scores "the action ran",
    and a refused trial is recorded as `allow`. A false witnessed row, produced by following
    the documented procedure -- so this refuses before the run rather than after it.
    """
    with pytest.raises(ValueError, match="must not wrap"):
        experiment_driver._reject_quoted_prompt(template)


@pytest.mark.parametrize("template", ["claude -p {prompt}", "claude -p {prompt} --permission-mode acceptEdits"])
def test_a_bare_prompt_slot_is_accepted(template):
    assert experiment_driver._reject_quoted_prompt(template) is None


def test_the_registry_templates_all_pass_the_guard():
    """The guard and the registry must agree, or `--driver harness` would refuse itself."""
    from agentseam import harness

    for agent in harness.agents():
        experiment_driver._reject_quoted_prompt(harness.driver_command(agent))
