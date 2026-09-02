"""Hooks, rendered standalone: bundler assembles the engine + one vendor entry into one file."""

from __future__ import annotations

import ast
import os

from . import __version__, adapters
from .allow_semantics import VOUCH_NOTES, VOUCH_SPEAKS, WARN_SPEAKS
from .bundler_templates import render, section
from .contract import EVENTS
from .matrix import capability

__all__ = ["SUPPORTED_AGENTS", "bundle", "bundle_entry"]

_HERE = os.path.dirname(__file__)
_ADAPTERS_DIR = os.path.join(_HERE, "adapters")

SUPPORTED_AGENTS = tuple(sorted(adapters.ADAPTERS))

#: The one dialect module (dialect-families.md §7: vscode_copilot stays code); its bundle
#: splices the module itself, every other agent composes an engine + `VENDOR` entry.
_DIALECT_MODULES = ("vscode_copilot",)

#: Families with their own engine module beside `_payload`/`_hook_json`; the F1/F2
#: families bind the shared `hj_*` entry points instead.
_SINGLETON_MODULES = {"cursor": "_cursor", "windsurf": "_windsurf", "antigravity": "_antigravity"}

#: Grammar -> the renderer `hj_respond` routes to it. A bundle carries only the renderers
#: its entry's gates speak; the reference left behind is unreachable for that entry's data.
_GRAMMAR_RENDERERS = {"G1": "_g1", "G2": "_g2"}


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _module_source(name):
    return _read(os.path.join(_HERE, "%s.py" % name))


def _adapter_module_source(name):
    return _read(os.path.join(_ADAPTERS_DIR, "%s.py" % name))


def _strip_own_imports(source, hoist=None):
    """`source` minus `from __future__ import annotations`, every relative import, and --"""
    tree = ast.parse(source)
    drop = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and (node.module == "__future__" or node.level >= 1):
            drop.update(range(node.lineno, node.end_lineno + 1))
        elif hoist is not None and isinstance(node, ast.Import):
            for alias in node.names:
                hoist.add((alias.name, alias.asname))
            drop.update(range(node.lineno, node.end_lineno + 1))
        elif hoist is not None and isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            for alias in node.names:
                hoist.add(("%s.%s" % (node.module, alias.name), alias.asname or alias.name))
            drop.update(range(node.lineno, node.end_lineno + 1))
    lines = source.splitlines(keepends=True)
    return "".join(line for i, line in enumerate(lines, start=1) if i not in drop)


def _render_imports(hoisted):
    """One `import` statement per module, however many names the sources bound it to."""
    by_module = {}
    for module, asname in hoisted:
        by_module.setdefault(module, set()).add(asname)
    out = []
    for module in sorted(by_module):
        names = sorted(n for n in by_module[module] if n is not None)
        plain = None in by_module[module]
        if "." in module:
            pkg, attr = module.rsplit(".", 1)
            out.append(
                "from %s import %s" % (pkg, attr)
                if names == [attr]
                else "from %s import %s as %s" % (pkg, attr, names[0])
            )
            for extra in names[1:]:
                out.append("%s = %s" % (extra, names[0]))
            continue
        first = None if plain else names[0]
        out.append("import %s" % module if first is None else "import %s as %s" % (module, first))
        bound = module if first is None else first
        for extra in names if first is None else names[1:]:
            out.append("%s = %s" % (extra, bound))
    return "\n".join(out)


def _owner_map(tree):
    """Every top-level def/assignment, by the name(s) it binds, in source order."""
    owner = {}
    order = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner[node.name] = node
            order.append(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    owner[target.id] = node
                    order.append(target.id)
    return owner, order


def _transitive_deps(owner, names, skip):
    """`names` plus every other top-level name their bodies reference, transitively."""
    needed, queue = set(), list(names)
    while queue:
        name = queue.pop()
        if name in needed or name in skip or name not in owner:
            continue
        needed.add(name)
        for sub in ast.walk(owner[name]):
            if isinstance(sub, ast.Name) and sub.id in owner and sub.id not in needed:
                queue.append(sub.id)
    return needed


def _extract_with_deps(source, names, skip=()):
    """The top-level defs/assignments named, plus whatever OTHER top-level names their"""
    tree = ast.parse(source)
    owner, order = _owner_map(tree)
    needed = _transitive_deps(owner, names, skip)

    seen = set()
    segments = []
    for name in order:
        if name in needed and name not in seen:
            seen.add(name)
            segments.append(ast.get_source_segment(source, owner[name]))
    return "\n\n".join(segments) + "\n"


def _runtime_section(agent):
    """The dispatch runtime, specialized to one agent's degrade facts."""
    transform_events = sorted(ev for ev in EVENTS if capability(agent, ev)["transform"])
    vouch_speaks = agent in VOUCH_SPEAKS
    warn_speaks = agent in WARN_SPEAKS
    note = VOUCH_NOTES["speaks"] if vouch_speaks else VOUCH_NOTES["degrades"]
    return section(
        "runtime (agentseam dispatch, specialized to %s)" % agent,
        render(
            "runtime.py.tmpl",
            {
                "__AGENT_REPR__": repr(agent),
                "__TRANSFORM_EVENTS__": repr(tuple(transform_events)),
                "__VOUCH_SPEAKS__": repr(vouch_speaks),
                "__VOUCH_SPEAKS_NOTE__": note,
                "__WARN_SPEAKS__": repr(warn_speaks),
            },
        ),
    )


def _engine_modules(cfg):
    """The engine modules this entry's data can reach, in splice order."""
    modules = []
    claims_cfg = cfg["claims"]
    if claims_cfg.get("reject_probes") or claims_cfg.get("reject_markers_unless_probe"):
        modules.append("_probes")
    if any(key in ("commandWindows", "windows") for key in cfg["hook_entry"].get("entry_extra", {})):
        modules.append("_windows")
    modules += ["_payload", "_hook_json", "_hook_entry"]
    if cfg["family"] in _SINGLETON_MODULES:
        modules.append(_SINGLETON_MODULES[cfg["family"]])
    return modules


def _engine_source(cfg, prefix, hoisted):
    """One family-engine body: the reachable modules, trimmed to what this entry binds."""
    combined = "\n\n".join(_strip_own_imports(_adapter_module_source(name), hoisted) for name in _engine_modules(cfg))
    entry_points = ["%s_claims" % prefix, "%s_parse" % prefix, "%s_respond" % prefix, "hook_entry_config"]
    if cfg["config_format"] == "toml":
        entry_points.append("render_config")
    spoken = {gate["grammar"] for gate in cfg["verdicts"]["gates"].values()}
    skip = tuple(fn for grammar, fn in sorted(_GRAMMAR_RENDERERS.items()) if grammar not in spoken)
    return _extract_with_deps(combined, entry_points, skip)


def bundle_entry(cfg):
    """Render one vendor config entry as a self-contained, stdlib-only hook file.

    Public so an entry not (yet) registered in `adapters` -- the thirteenth vendor --
    bundles exactly the way the registered ones do.
    """
    agent = cfg["agent"]
    prefix = cfg["family"] if cfg["family"] in _SINGLETON_MODULES else "hj"
    hoisted = {("json", None), ("sys", None)}

    body = []
    body.append(
        section("contract (agentseam %s)" % __version__, _strip_own_imports(_module_source("contract"), hoisted))
    )
    body.append(
        section(
            "%s family engine (trimmed to what this entry uses)" % cfg["family"], _engine_source(cfg, prefix, hoisted)
        )
    )
    body.append(
        section(
            "%s vendor config + engine binding" % agent,
            render("binding.py.tmpl", {"__AGENT__": agent, "__PREFIX__": prefix, "__VENDOR__": repr(cfg)}),
        )
    )

    sections = [render("header.py.tmpl", {"__AGENT__": agent, "__VERSION__": __version__})]
    sections.append("from __future__ import annotations\n\n%s\n" % _render_imports(hoisted))
    sections.extend(body)
    sections.append(_runtime_section(agent))
    return "\n".join(sections)


def _dialect_bundle(agent):
    """Contract + the dialect module itself: the composition for the one module vendor."""
    hoisted = {("json", None), ("sys", None)}

    body = []
    body.append(
        section("contract (agentseam %s)" % __version__, _strip_own_imports(_module_source("contract"), hoisted))
    )
    body.append(
        section(
            "windows helper (used by the %s adapter)" % agent,
            _strip_own_imports(_adapter_module_source("_windows"), hoisted),
        )
    )
    body.append(section("%s adapter" % agent, _strip_own_imports(_adapter_module_source(agent), hoisted)))

    sections = [render("header.py.tmpl", {"__AGENT__": agent, "__VERSION__": __version__})]
    sections.append("from __future__ import annotations\n\n%s\n" % _render_imports(hoisted))
    sections.extend(body)
    sections.append(_runtime_section(agent))
    return "\n".join(sections)


def bundle(agent):
    """Render `agent`'s dispatch runtime as one self-contained, stdlib-only Python file."""
    if agent not in SUPPORTED_AGENTS:
        raise KeyError("%s: no adapter to bundle (have: %s)" % (agent, ", ".join(SUPPORTED_AGENTS)))
    if agent in _DIALECT_MODULES:
        return _dialect_bundle(agent)
    return bundle_entry(adapters.get(agent).CONFIG)
