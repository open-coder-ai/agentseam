"""Bundler unit tests: the composed source itself -- compiles, is self-contained, is"""

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
    """The one claim this whole primitive exists to make good on: vendored into an adopter"""
    tree = ast.parse(bundler.bundle(agent))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert not any(a.name.split(".")[0] == "agentseam" for a in node.names), agent
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, "a relative import means an inlined section was not fully composed: %s" % agent
            assert (node.module or "").split(".")[0] != "agentseam", agent


@pytest.mark.parametrize("agent", bundler.SUPPORTED_AGENTS)
def test_bundle_has_no_colliding_top_level_names(agent):
    """Two sections defining the same name would silently shadow one another -- Python does"""
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
    """gemini_cli and devin borrow claude_code's payload-envelope discriminator; their"""
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


def test_no_module_is_imported_twice_at_module_level():
    """Composing sources that each legitimately `import json` used to emit one module-level"""
    for agent in bundler.SUPPORTED_AGENTS:
        tree = ast.parse(bundler.bundle(agent))
        modules = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                modules.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module != "__future__":
                modules.append(node.module)
        duplicated = sorted({m for m in modules if modules.count(m) > 1})
        assert not duplicated, "%s bundle imports %s more than once at module level" % (agent, duplicated)


def test_every_name_a_source_imported_is_still_bound():
    """Hoisting must not lose an alias. Each bundle is compiled and executed in a namespace"""
    for agent in bundler.SUPPORTED_AGENTS:
        src = bundler.bundle(agent)
        namespace = {"__name__": "_bundle_%s" % agent}
        exec(compile(src, "<bundle:%s>" % agent, "exec"), namespace)  # noqa: S102 - the artifact under test
        assert namespace["_json"] is namespace["json"], "%s: alias binding lost" % agent


def test_function_local_imports_are_left_alone():
    """A source's decision to import inside a function body is its own; a source-composer"""
    src = bundler.bundle("claude_code")
    tree = ast.parse(src)
    local = [
        node
        for parent in ast.walk(tree)
        if isinstance(parent, ast.FunctionDef)
        for node in ast.walk(parent)
        if isinstance(node, ast.Import)
    ]
    assert local, "expected at least one function-local import to have survived hoisting"
