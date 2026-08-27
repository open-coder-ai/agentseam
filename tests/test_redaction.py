"""Redaction: keys and types survive, values do not.

Split from the probe tests because reducing a payload to its shape is a different activity
from running a hook inside somebody else's agent -- and because the combined file hit the
300-line review budget, where the remedy is splitting by activity rather than raising the
number.

The strong claim is asserted rather than inspected: no string from the input may appear in
the output, checked against the real redact() over a payload full of things that must not
travel.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tools"))

import pytest  # noqa: E402
from redact import STRUCTURAL_KEYS, keys_of, redact  # noqa: E402

# Paths use /workspace/alice deliberately: the repository's own privacy scanner rejects a tracked
# file containing a realistic home directory, and it was right to reject the first version of

SENSITIVE = {
    "hook_event_name": "PreToolUse",
    "tool_name": "Write",
    "session_id": "sess-9f3a-private",
    "cwd": "/workspace/alice/work",
    "user_email": "someone@example.com",
    "transcript_path": "/workspace/alice/.claude/transcript.jsonl",
    "prompt": "deploy using my key AKIA-not-real",
    "tool_input": {"file_path": "/workspace/alice/.env", "content": "TOKEN=hunter2"},
    "workspace_roots": ["/workspace/alice/repo", "/workspace/alice/other"],
    "nested": {"deep": {"deeper": "still private"}},
    "count": 7,
    "flag": True,
}


def _strings(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [s for v in value.values() for s in _strings(v)]
    if isinstance(value, list):
        return [s for v in value for s in _strings(v)]
    return []


def test_no_input_string_survives_except_allowlisted_enums():
    """The property that matters. A denylist would miss the first field a vendor invents."""
    out = redact(SENSITIVE)
    allowed = {SENSITIVE[k] for k in STRUCTURAL_KEYS if isinstance(SENSITIVE.get(k), str)}
    leaked = [s for s in _strings(out) if s in set(_strings(SENSITIVE)) and s not in allowed]
    assert not leaked, "these input strings survived redaction: %s" % leaked


def test_the_protocol_enums_do_survive():
    """Otherwise a capture cannot tell us which event we are looking at, which is the point."""
    out = redact(SENSITIVE)
    assert out["hook_event_name"] == "PreToolUse"
    assert out["tool_name"] == "Write"


def test_a_structural_key_carrying_prose_is_still_redacted():
    """The allowlist is by key AND by shape, so a vendor reusing a name for something
    richer cannot smuggle content through it.
    """
    out = redact({"tool_name": "/workspace/alice/secret/path/with/separators"})
    assert out["tool_name"].startswith("<str:")

    long_value = {"source": "x" * 200}
    assert redact(long_value)["source"].startswith("<str:")


def test_structure_and_types_are_preserved_because_that_is_the_evidence():
    out = redact(SENSITIVE)
    assert out["count"] == 7 and out["flag"] is True
    assert set(keys_of(out)) >= {"tool_input", "tool_input.content", "nested.deep.deeper"}
    assert out["tool_input"]["content"].startswith("<str:")


def test_long_lists_are_summarized_not_dumped():
    out = redact({"items": ["a", "b", "c", "d"]})
    assert out["items"][-1] == "<...2 more>"


@pytest.mark.parametrize("value", [None, 3, 3.5, True, "plain", [], {}])
def test_redaction_never_raises_on_anything_a_vendor_might_send(value):
    json.dumps(redact({"k": value}))
