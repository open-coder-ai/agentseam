#!/usr/bin/env python3
"""Thin shim: the real implementation is `agentseam.probe.experiment_probe` (T1 wave 1)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from agentseam.probe.experiment_probe import BEHAVIOURS as BEHAVIOURS  # noqa: E402
from agentseam.probe.experiment_probe import SILENT_TRIALS as SILENT_TRIALS  # noqa: E402
from agentseam.probe.experiment_probe import TIMEOUT_SLEEP_SECONDS as TIMEOUT_SLEEP_SECONDS  # noqa: E402
from agentseam.probe.experiment_probe import render as render  # noqa: E402
