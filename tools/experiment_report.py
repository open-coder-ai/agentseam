#!/usr/bin/env python3
"""Thin shim: the real implementation is `agentseam.probe.experiment_report` (T1 wave 1)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from agentseam.probe.experiment_report import _cell_key as _cell_key  # noqa: E402 -- tests call it directly
from agentseam.probe.experiment_report import as_report as as_report  # noqa: E402
from agentseam.probe.experiment_report import diff_against_matrix as diff_against_matrix  # noqa: E402
from agentseam.probe.experiment_report import render as render  # noqa: E402
