"""The bundle templates are files, valid Python as-is, with every __TOKEN__ accounted for."""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentseam import bundler  # noqa: E402
from agentseam.bundler_templates import TEMPLATE_TOKENS, render, template  # noqa: E402

TEMPLATE_DIR = ROOT / "src" / "agentseam" / "data" / "templates"

#: A token is uppercase words joined by single underscores, wrapped in double underscores;
#: written so `__PREFIX___claims` (token butted against an identifier tail) matches only
#: the `__PREFIX__` inside it.
_TOKEN = re.compile(r"__[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)*__")


def test_the_token_table_names_exactly_the_template_files_that_exist():
    """A template outside the table has tokens nothing checks; a row without a file lies."""
    assert sorted(TEMPLATE_TOKENS) == sorted(p.name for p in TEMPLATE_DIR.glob("*.py.tmpl"))


@pytest.mark.parametrize("name", sorted(TEMPLATE_TOKENS))
def test_every_token_a_template_carries_is_supplied_and_none_is_orphaned(name):
    """Token set in the file == token set the renderer supplies, both directions."""
    assert set(_TOKEN.findall(template(name))) == set(TEMPLATE_TOKENS[name])


@pytest.mark.parametrize("name", sorted(TEMPLATE_TOKENS))
def test_every_template_is_valid_python_as_committed(name):
    """__TOKEN__ placeholders are legal identifiers, so the file must parse untouched."""
    ast.parse(template(name), filename=name)


@pytest.mark.parametrize("agent", sorted(bundler.SUPPORTED_AGENTS))
def test_a_rendered_bundle_carries_no_residual_token(agent):
    assert not _TOKEN.findall(bundler.bundle(agent))


def test_render_replaces_every_occurrence_of_a_token():
    out = render("header.py.tmpl", {"__AGENT__": "probe_agent", "__VERSION__": "9.9.9"})
    assert "probe_agent" in out and "9.9.9" in out
    assert not _TOKEN.findall(out)
