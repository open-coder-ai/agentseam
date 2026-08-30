"""Repo-wide standards, mechanically enforced.

A convention nobody checks is a convention that erodes. These are the ones worth
paying for in CI time.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "agentseam"
MAX_LINES = 300


def _python_files():
    return sorted(p for p in ROOT.rglob("*.py") if ".git" not in p.parts and "build" not in p.parts)


def test_no_file_exceeds_line_budget():
    """300 lines. The remedy is splitting by activity, not raising the number."""
    violations = [
        "%s (%d)" % (p.relative_to(ROOT), len(p.read_text().splitlines()))
        for p in _python_files()
        if len(p.read_text().splitlines()) > MAX_LINES
    ]
    assert not violations, "Files exceed the %d-line review budget (split by activity):\n%s" % (
        MAX_LINES,
        "\n".join(violations),
    )


def test_runtime_path_imports_only_stdlib():
    """Adapters get vendored as single files; a third-party import breaks consumers."""
    stdlib = getattr(sys, "stdlib_module_names", None)
    if stdlib is None:  # py<3.10: covered by the CI job instead
        return
    offenders = []
    for path in sorted(SRC.rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                if node.level:  # relative import, ours
                    continue
                names = [(node.module or "").split(".")[0]]
            else:
                continue
            for name in names:
                if name and name not in stdlib and name != "agentseam":
                    offenders.append("%s: %s" % (path.relative_to(ROOT), name))
    assert not offenders, "Non-stdlib imports in the runtime path:\n" + "\n".join(offenders)


def test_every_adapter_implements_the_interface():
    """Adding an agent must not require changing anything else; that only holds if
    every adapter actually satisfies the contract."""
    from agentseam import adapters

    required = ("AGENT", "claims", "parse", "respond", "hook_config", "CONFIG_PATH")
    for name, mod in adapters.ADAPTERS.items():
        missing = [attr for attr in required if not hasattr(mod, attr)]
        assert not missing, "adapter %s is missing %s" % (name, missing)


def test_every_adapter_has_a_matrix_row():
    """An adapter with no matrix row can make claims nothing verifies."""
    from agentseam import adapters
    from agentseam.matrix import MATRIX

    for name in adapters.ADAPTERS:
        assert name in MATRIX, "adapter %s has no capability matrix row" % name


def test_governance_files_exist():
    for name in (
        "README.md",
        "LICENSE",
        "CONTRIBUTING.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "GOVERNANCE.md",
        "SUPPORT.md",
        "CHANGELOG.md",
        "AGENTS.md",
    ):
        assert (ROOT / name).exists(), "missing %s" % name


def test_import_pulls_in_only_stdlib():
    """Runtime counterpart to the AST check: catches a lazy import inside a function.

    Runs the exact script CI runs, so the two cannot drift apart again.
    """
    from check_stdlib_only import offending_imports

    assert not offending_imports()


def _decision_outcomes():
    """Read off the class, so a constructor added later is discovered rather than assumed."""
    sys.path.insert(0, str(ROOT / "src"))
    from agentseam import contract

    return [name for name, value in vars(contract.Decision).items() if isinstance(value, classmethod)]


def test_the_front_door_docs_name_every_decision_outcome():
    """A partial vocabulary in the docs is an outcome nobody knows they can return.

    `vouch` was added to `Decision` and neither of these files heard about it, so the
    project's own front page described a four-word vocabulary for a five-word type. Only
    these two files are checked: the generated example pages carry each VENDOR's dialect,
    where an absent word is the honest answer, and prose elsewhere may mention one outcome
    without claiming to enumerate them.
    """
    missing = []
    for name in ("README.md", "llms.txt"):
        text = (ROOT / name).read_text(encoding="utf-8")
        for outcome in _decision_outcomes():
            if "`%s`" % outcome not in text:
                missing.append("%s never names `%s`" % (name, outcome))
    assert not missing, "\n  ".join(["docs describe an incomplete decision vocabulary:"] + missing)


def test_citation_version_tracks_the_package():
    """CITATION.cff is a claim about which version someone cited, so a stale one misattributes.

    It has no build step to keep it honest -- it drifted on the 0.1.1 bump, in the same
    commit that did the bumping -- so the check has to live here.
    """
    sys.path.insert(0, str(ROOT / "src"))
    import agentseam

    lines = (ROOT / "CITATION.cff").read_text(encoding="utf-8").splitlines()
    declared = [line.split(":", 1)[1].strip() for line in lines if line.startswith("version:")]
    assert declared == [agentseam.__version__], "CITATION.cff says %r, package is %r" % (
        declared,
        agentseam.__version__,
    )
