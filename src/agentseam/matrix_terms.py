"""The vocabulary the matrix asserts in: fail modes, coverage tiers, and the cell shape."""

from __future__ import annotations

FAIL_CLOSED = "closed"
FAIL_OPEN = "open"
FAIL_CONFIGURABLE = "configurable"

TIER_FULL = "block+rewrite"
TIER_BLOCK = "block"
TIER_OBSERVE = "observe"
TIER_NONE = "none"
TIER_UNADAPTED = "unadapted"


def _cap(block=False, rewrite=False, fail=FAIL_OPEN):
    return {"block": block, "rewrite": rewrite, "fail_mode": fail}


BASIS_LIVE = "live-run"
BASIS_SOURCE = "vendor-source"
BASIS_DOCS = "vendor-docs"
BASIS_THIRD_PARTY = "third-party-install"
BASIS_LIVE_PARTIAL = "live-run-partial"
BASIS_INHERITED = "inherited"
BASES = (BASIS_LIVE, BASIS_LIVE_PARTIAL, BASIS_SOURCE, BASIS_DOCS, BASIS_THIRD_PARTY, BASIS_INHERITED)
