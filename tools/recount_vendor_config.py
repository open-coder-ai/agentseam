#!/usr/bin/env python3
"""Recount `data/vendors/<agent>.json` from the current adapters -- never by hand.

    python3 tools/recount_vendor_config.py            # print every entry, one per agent
    python3 tools/recount_vendor_config.py --write     # (re)write data/vendors/<agent>.json

Wave D2 (docs/design/dialect-families.md §6): the vendor config schema and all 12 entries,
unused by the runtime yet -- their correctness is proven by recounting, not by wiring
(D3+ wires them). Every mechanical field is derived by *executing* or *AST-reading* the
current adapter module or its frozen golden fixture (`tests/fixtures/golden/<agent>.json`,
wave D1's frozen wire truth), the same discipline `tools/capture_fixtures.py` uses for the
fixtures themselves -- see `tools/recount/__init__.py` for the section-by-section how.

The **consistency test** (`tests/test_vendor_config.py::test_entries_match_recount`) re-runs
this exact package and asserts the committed JSON is what it produces now.
"""

from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "src"))
sys.path.insert(0, os.path.join(ROOT, "examples"))
sys.path.insert(0, os.path.join(ROOT, "tools"))

from recount import build_all  # noqa: E402

DATA_DIR = os.path.join(ROOT, "src", "agentseam", "data", "vendors")


def main():
    entries = build_all()
    if "--write" in sys.argv[1:]:
        for agent, entry in entries.items():
            path = os.path.join(DATA_DIR, "%s.json" % agent)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(entry, fh, indent=2, sort_keys=True)
                fh.write("\n")
            print("wrote", path)
    else:
        print(json.dumps(entries, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
