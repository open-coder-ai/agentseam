"""Cursor adapter: true pre-block on shell, detect-only on file edits."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from payloads import CU_EDIT, CU_SHELL  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import Decision  # noqa: E402


def allow_all(_e):
    return Decision.allow()


def deny_all(_e):
    return Decision.deny("test-deny")


def test_cursor_shell_blocks_pre_execution():
    text, code, event, _ = A.handle(CU_SHELL, deny_all)
    assert json.loads(text)["permission"] == "deny"
    assert event.event == A.PRE_TOOL and code == 0


def test_cursor_file_edit_is_detect_only():
    """Cursor has no beforeFileEdit: a deny must surface as post-write detection."""
    text, code, event, _ = A.handle(CU_EDIT, deny_all)
    assert event.event == A.POST_TOOL
    assert code == 2  # flagged, not blocked
    assert "cannot block" in json.loads(text)["user_message"]


def test_cursor_clean_edit_is_silent():
    text, code, _, _ = A.handle(CU_EDIT, allow_all)
    assert (text, code) == ("", 0)
