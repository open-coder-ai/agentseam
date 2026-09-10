#!/usr/bin/env python3
"""Thin shim: the real implementation is `agentseam.probe.experiment_driver` (T1 wave 1)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from agentseam.probe.experiment_driver import drive_real as drive_real  # noqa: E402
