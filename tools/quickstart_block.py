#!/usr/bin/env python3
"""Print the first ```bash fence under README.md's `## Quick start` heading.

CI extracts this to prove the block actually runs (see the `quickstart` job in
.github/workflows/ci.yml) instead of trusting that a code sample still works.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADING = re.compile(r"^## Quick start\s*$", re.MULTILINE)
FENCE = re.compile(r"```bash\n(.*?)```", re.DOTALL)


def extract(text):
    """The literal contents of the first ```bash fence after `## Quick start`, or None."""
    heading = HEADING.search(text)
    if not heading:
        return None
    fence = FENCE.search(text, heading.end())
    return fence.group(1) if fence else None


def main():
    block = extract((ROOT / "README.md").read_text(encoding="utf-8"))
    if block is None:
        print("no ```bash fence found under a '## Quick start' heading in README.md", file=sys.stderr)
        return 1
    sys.stdout.write(block)
    return 0


if __name__ == "__main__":
    sys.exit(main())
