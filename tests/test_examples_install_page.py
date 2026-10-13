"""A page's "What `agentseam install` writes" shows what install writes, and its payloads are the vendor's."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "examples"))

import pytest  # noqa: E402
from generate import build  # noqa: E402
from vendor_payloads import SECRET, payload  # noqa: E402

import agentseam as A  # noqa: E402
from agentseam import adapters  # noqa: E402
from agentseam import install as I  # noqa: E402


def _install_block(page):
    section = page.split("## What `agentseam install` writes", 1)[1].split("```json\n", 1)[1]
    return json.loads(section.split("\n```", 1)[0])


@pytest.mark.parametrize("agent", ["antigravity", "claude_code", "devin", "grok"])
def test_the_install_section_is_the_file_install_writes(agent, tmp_path):
    """raw[1].findings[5]: the antigravity page showed the fragment without install's `_agentseam` markers."""
    shown = _install_block(build()["%s.md" % agent])
    events = [ev for ev in adapters.get(agent).REVERSE_EVENT_MAP if ev != A.FILE_CHANGED or agent != "claude_code"]
    path = I.install(agent, events, "python3 guard.py", str(tmp_path))
    with open(path, encoding="utf-8") as fh:
        assert shown == json.load(fh)


def test_cursor_after_file_edit_example_carries_the_documented_edits():
    """raw[2].findings[5]: cursor.com/docs/hooks gives afterFileEdit {file_path, edits: [{old_string, new_string}]}."""
    raw = payload("cursor", A.FILE_CHANGED, "afterFileEdit")
    assert raw["edits"] == [{"old_string": "", "new_string": SECRET}]
    assert adapters.get("cursor").parse(raw).content == SECRET
