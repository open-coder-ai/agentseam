#!/usr/bin/env python3
"""Thin shim: the real implementation is `agentseam.probe.experiment` (promoted, T1 wave 1).

Kept so `python3 tools/experiment.py ...` keeps working from a source checkout without a
second copy of the harness existing anywhere. Every name re-exported below (including the
one underscore-prefixed helper the test suite reaches into directly) is the promoted
module's own object, so this file can never drift from what actually ships in the wheel.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from agentseam.probe.experiment import EVENTS as EVENTS  # noqa: E402
from agentseam.probe.experiment import SENTINEL as SENTINEL  # noqa: E402
from agentseam.probe.experiment import SENTINEL_ALT as SENTINEL_ALT  # noqa: E402
from agentseam.probe.experiment import TRIGGER as TRIGGER  # noqa: E402
from agentseam.probe.experiment import TRIGGER_ALT as TRIGGER_ALT  # noqa: E402
from agentseam.probe.experiment import _classify as _classify  # noqa: E402 -- tests call it directly
from agentseam.probe.experiment import run_trial as run_trial  # noqa: E402
from agentseam.probe.experiment_cli import main as main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
