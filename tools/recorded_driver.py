#!/usr/bin/env python3
"""Thin shim: the real implementation is `agentseam.probe.recorded_driver` (T1 wave 1)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from agentseam.probe.recorded_driver import DRIVER_NAME as DRIVER_NAME  # noqa: E402
from agentseam.probe.recorded_driver import NON_LIVE_DRIVERS as NON_LIVE_DRIVERS  # noqa: E402
from agentseam.probe.recorded_driver import REFERENCE_DRIVER as REFERENCE_DRIVER  # noqa: E402
from agentseam.probe.recorded_driver import NoRecording as NoRecording  # noqa: E402
from agentseam.probe.recorded_driver import add_cli_args as add_cli_args  # noqa: E402
from agentseam.probe.recorded_driver import check_record_args as check_record_args  # noqa: E402
from agentseam.probe.recorded_driver import finalize_record as finalize_record  # noqa: E402
from agentseam.probe.recorded_driver import has_recording as has_recording  # noqa: E402
from agentseam.probe.recorded_driver import record as record  # noqa: E402
from agentseam.probe.recorded_driver import recordings as recordings  # noqa: E402
from agentseam.probe.recorded_driver import resolve_driver as resolve_driver  # noqa: E402
