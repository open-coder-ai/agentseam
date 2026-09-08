"""The extractor CI runs the README's Quick start block through."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

from quickstart_block import extract  # noqa: E402


def test_extracts_the_real_readme_block():
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    block = extract(text)
    assert block is not None
    assert "agentseam install all" in block
    assert "pip install agentseam" in block


def test_none_when_no_quick_start_heading():
    assert extract("# agentseam\n\n```bash\necho hi\n```\n") is None


def test_none_when_quick_start_has_no_bash_fence():
    assert extract("## Quick start\n\n```python\nprint('hi')\n```\n") is None


def test_stops_at_the_first_fence():
    text = "## Quick start\n\n```bash\none\n```\n\n```bash\ntwo\n```\n"
    assert extract(text) == "one\n"
