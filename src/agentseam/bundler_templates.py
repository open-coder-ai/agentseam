"""Bundler templates: loaded from data/templates/*.py.tmpl, rendered by __TOKEN__ replace."""

from __future__ import annotations

from importlib import resources

#: Template file -> the tokens `render()` callers supply. tests/test_bundler_templates.py
#: pins this table against the files: every token supplied, none orphaned.
TEMPLATE_TOKENS = {
    "binding.py.tmpl": ("__AGENT__", "__PREFIX__", "__VENDOR__"),
    "header.py.tmpl": ("__AGENT__", "__VERSION__"),
    "runtime.py.tmpl": (
        "__AGENT_REPR__",
        "__TRANSFORM_EVENTS__",
        "__VOUCH_SPEAKS__",
        "__VOUCH_SPEAKS_NOTE__",
        "__WARN_SPEAKS__",
    ),
}


def template(name):
    """The raw template text; each file is valid Python as-is, so ruff lints it as such."""
    return (resources.files(__package__) / "data" / "templates" / name).read_text(encoding="utf-8")


def render(name, replacements):
    """`template(name)` with every __TOKEN__ swapped by str.replace, never str.format."""
    text = template(name)
    for token, value in replacements.items():
        text = text.replace(token, value)
    return text


def section(title, body):
    return "# %s\n# %s\n\n%s\n" % ("-" * 78, title, body.strip("\n") + "\n")
