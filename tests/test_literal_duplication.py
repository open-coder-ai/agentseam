"""No repeated string literal (coding-standards.md §3) reaches src/ without a constant or a reason."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from literal_duplication import find_duplicates  # noqa: E402

ALLOWLIST_PATH = ROOT / "tools" / "literal_duplication_allowlist.json"
SRC = ROOT / "src" / "agentseam"


def _allowlist():
    return json.loads(ALLOWLIST_PATH.read_text(encoding="utf-8"))


def test_allowlist_entries_all_carry_a_reason():
    unreasoned = [text for text, reason in _allowlist().items() if not (reason or "").strip()]
    assert not unreasoned, "allowlist entries need a non-empty reason: %r" % unreasoned


def test_no_undocumented_literal_duplication():
    """A literal repeated >= 3x wants a constant/data table (coding-standards.md §3) or a reason."""
    allowlist = _allowlist()
    undocumented = {text: locs for text, locs in find_duplicates(str(SRC)).items() if text not in allowlist}
    assert not undocumented, "duplicated literal(s) need a constant, data table, or an allowlist reason:\n" + "\n".join(
        "%r (%dx): %s" % (text, len(locs), locs) for text, locs in sorted(undocumented.items())
    )
