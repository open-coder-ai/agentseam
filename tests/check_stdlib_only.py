#!/usr/bin/env python3
"""Assert that importing agentseam pulls in nothing outside the standard library.

Runnable standalone (CI) and imported by the test suite, deliberately: the first
version of this check lived inline in the workflow, drifted from the local test, and
shipped a red pipeline. One implementation, two callers.

Semantics: diff sys.modules before and after the import, so pre-existing environment
artifacts (sitecustomize, coverage hooks, whatever the runner injects) are not
attributed to us. Compare TOP-LEVEL package names, since sys.stdlib_module_names
lists `os`, not `os.path`.
"""

import sys
from pathlib import Path


def offending_imports():
    """Top-level non-stdlib packages that importing agentseam brings in."""
    src = Path(__file__).resolve().parents[1] / "src"
    if str(src) not in sys.path:
        sys.path.insert(0, str(src))

    before = set(sys.modules)
    import agentseam  # noqa: F401

    stdlib = getattr(sys, "stdlib_module_names", None)
    if stdlib is None:  # py<3.10 has no inventory; the AST test covers those runs
        return []
    added = set(sys.modules) - before
    return sorted(
        {
            name.split(".")[0]
            for name in added
            if not name.startswith(("agentseam", "_")) and name.split(".")[0] not in stdlib
        }
    )


def main():
    bad = offending_imports()
    if bad:
        print("non-stdlib imports pulled in by `import agentseam`: %s" % bad, file=sys.stderr)
        return 1
    import agentseam

    print("stdlib-only import OK", agentseam.__version__)
    return 0


if __name__ == "__main__":
    sys.exit(main())
