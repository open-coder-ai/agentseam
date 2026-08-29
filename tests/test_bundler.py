"""Bundler unit tests: the composed source itself -- compiles, is self-contained, is
deterministic, and never collides two sections' top-level names.

The stronger claim -- that the bundle actually RUNS correctly, standalone, with no
agentseam installed -- is tests/test_bundler_subprocess.py; this file only has to prove
the text `bundle()` produces is well-formed and honest about what it depends on.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agentseam import __version__, adapters, bundler  # noqa: E402


def _top_level_names(tree):
    names = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        elif isinstance(node, ast.Assign):
            names.extend(t.id for t in node.targets if isinstance(t, ast.Name))
    return names


def test_supported_agents_is_exactly_the_agents_with_an_adapter():
    assert bundler.SUPPORTED_AGENTS == tuple(sorted(adapters.ADAPTERS))


def test_unknown_agent_raises_keyerror_naming_what_is_bundleable():
    with pytest.raises(KeyError, match="claude_code"):
        bundler.bundle("not_a_real_agent")


def test_bundle_is_byte_stable():
    """Same input (agent, agentseam version) -> identical bytes, every time."""
    first = bundler.bundle("claude_code")
    for _ in range(3):
        assert bundler.bundle("claude_code") == first


def test_bundle_stamps_the_agentseam_version_in_the_header():
    src = bundler.bundle("claude_code")
    header = src.split("\n\n", 1)[0]
    assert __version__ in header


@pytest.mark.parametrize("agent", bundler.SUPPORTED_AGENTS)
def test_bundle_compiles_as_a_standalone_module(agent):
    src = bundler.bundle(agent)
    compile(src, "%s-bundle.py" % agent, "exec")


@pytest.mark.parametrize("agent", bundler.SUPPORTED_AGENTS)
def test_bundle_never_imports_agentseam(agent):
    """The one claim this whole primitive exists to make good on: vendored into an adopter
    repo with agentseam not installed, this file must still run."""
    tree = ast.parse(bundler.bundle(agent))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(a.name.split(".")[0] == "agentseam" for a in node.names), agent
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import means an inlined section was not fully composed: %s" % agent
            assert (node.module or "").split(".")[0] != "agentseam", agent


@pytest.mark.parametrize("agent", bundler.SUPPORTED_AGENTS)
def test_bundle_has_no_colliding_top_level_names(agent):
    """Two sections defining the same name would silently shadow one another -- Python does
    not error on a duplicate top-level def, it just makes the first one dead code."""
    names = _top_level_names(ast.parse(bundler.bundle(agent)))
    dupes = sorted({n for n in names if names.count(n) > 1})
    assert not dupes, "%s: %s" % (agent, dupes)


@pytest.mark.parametrize("agent", bundler.SUPPORTED_AGENTS)
def test_bundle_leaves_a_marked_unimplemented_handler_slot(agent):
    src = bundler.bundle(agent)
    assert "# >>> agentseam handler >>>" in src
    assert "# <<< agentseam handler <<<" in src
    assert "def handle(event):" in src
    assert "NotImplementedError" in src


def test_cross_adapter_dependency_is_inlined_where_actually_used():
    """gemini_cli and devin borrow claude_code's payload-envelope discriminator; their
    bundles need it and claude_code's own AGENT identity name must not leak in with it."""
    for agent in ("gemini_cli", "devin"):
        src = bundler.bundle(agent)
        assert "def looks_like_claude_code(raw):" in src
        assert "OBSERVED_MARKERS" in src
        assert 'AGENT = "claude_code"' not in src


def test_windows_helper_is_inlined_only_where_the_adapter_actually_needs_it():
    for agent in ("codex_cli", "vscode_copilot"):
        assert "def powershell_command(command):" in bundler.bundle(agent)
    for agent in ("claude_code", "gemini_cli"):
        assert "def powershell_command(command):" not in bundler.bundle(agent)
