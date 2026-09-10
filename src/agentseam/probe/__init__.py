"""Armed: measures what an agent's hooks actually enforce, instead of asserting it.

Promoted from tools/ (wave 1, T1) so it ships in the wheel behind `agentseam probe`
(cli.py) instead of being a developer-only script. tools/*.py at the old paths are now
thin shims over these modules -- see tools/experiment.py's own docstring.
"""

from __future__ import annotations

from . import (
    cli,
    experiment,
    experiment_cli,
    experiment_driver,
    experiment_escalate,
    experiment_probe,
    experiment_report,
    recorded_driver,
    reference_agent,
)

__all__ = [
    "cli",
    "experiment",
    "experiment_cli",
    "experiment_driver",
    "experiment_escalate",
    "experiment_probe",
    "experiment_report",
    "recorded_driver",
    "reference_agent",
]
