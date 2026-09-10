#!/usr/bin/env python3
"""Thin shim: the real implementation is `agentseam.probe.reference_agent` (T1 wave 1)."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from agentseam.probe.reference_agent import ALLOW as ALLOW  # noqa: E402
from agentseam.probe.reference_agent import ASK as ASK  # noqa: E402
from agentseam.probe.reference_agent import CLAUDE_CODE_TIMEOUT_SECONDS as CLAUDE_CODE_TIMEOUT_SECONDS  # noqa: E402
from agentseam.probe.reference_agent import DENY as DENY  # noqa: E402
from agentseam.probe.reference_agent import GRAMMARS as GRAMMARS  # noqa: E402
from agentseam.probe.reference_agent import TURN as TURN  # noqa: E402
from agentseam.probe.reference_agent import Undocumented as Undocumented  # noqa: E402
from agentseam.probe.reference_agent import _interpret as _interpret  # noqa: E402 -- tests call it directly
from agentseam.probe.reference_agent import main as main  # noqa: E402
from agentseam.probe.reference_agent import run_pre_tool as run_pre_tool  # noqa: E402
from agentseam.probe.reference_agent import run_turn as run_turn  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
