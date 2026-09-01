"""Hooks, rendered standalone: bundler assembles dispatch + one adapter into one file."""

from __future__ import annotations

import ast
import os

from . import __version__, adapters
from .allow_semantics import VOUCH_SPEAKS, WARN_SPEAKS
from .bundler_templates import HEADER, RUNTIME, section
from .contract import EVENTS
from .matrix import capability

__all__ = ["bundle", "SUPPORTED_AGENTS"]

_HERE = os.path.dirname(__file__)
_ADAPTERS_DIR = os.path.join(_HERE, "adapters")

SUPPORTED_AGENTS = tuple(sorted(adapters.ADAPTERS))


def _read(path):
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _module_source(name):
    return _read(os.path.join(_HERE, "%s.py" % name))


def _adapter_source(agent):
    path = os.path.join(_ADAPTERS_DIR, "%s.py" % agent)
    if not os.path.exists(path):
        raise KeyError("%s: no adapter module to bundle (have: %s)" % (agent, ", ".join(SUPPORTED_AGENTS)))
    return _read(path)


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


def _cross_module_imports(source):
    """`{module: [names]}` for every `from .<module> import ...` this source makes,"""
    tree = ast.parse(source)
    deps = {}
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.level == 1 and node.module and node.module != "_windows":
            deps.setdefault(node.module, []).extend(alias.name for alias in node.names)
    return deps


def _needs_windows_helper(source):
    tree = ast.parse(source)
    return any(isinstance(node, ast.ImportFrom) and node.level == 1 and node.module == "_windows" for node in tree.body)


def _extract_with_deps(source, names):
    """The top-level defs/assignments named, plus whatever OTHER top-level names their"""
    tree = ast.parse(source)
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

    needed, queue = set(), list(names)
    while queue:
        name = queue.pop()
        if name in needed or name not in owner:
            continue
        needed.add(name)
        for sub in ast.walk(owner[name]):
            if isinstance(sub, ast.Name) and sub.id in owner and sub.id not in needed:
                queue.append(sub.id)

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
    note = (
        "claude_code and vscode_copilot are the only agents with real evidence that an "
        'explicit approval word means "skip confirmation"; see agentseam.allow_semantics'
        if vouch_speaks
        else "no evidence establishes that an explicit approval word means anything beyond "
        "a plain allow here, so vouch degrades to one; see agentseam.allow_semantics"
    )
    return section(
        "runtime (agentseam dispatch, specialized to %s)" % agent,
        RUNTIME.format(
            agent=agent,
            vouch_speaks=vouch_speaks,
            vouch_speaks_note=note,
            warn_speaks=warn_speaks,
            transform_events=tuple(transform_events),
        ),
    )


_BINDING = """\
AGENT = "{agent}"

VENDOR = {vendor}


def claims(raw):
    return hj_claims(VENDOR, raw)


def parse(raw):
    return hj_parse(VENDOR, raw)


def respond(decision, event):
    return hj_respond(VENDOR, decision, event)


def hook_config(canonical_events, command, matcher=None):
    return hook_entry_config(VENDOR, canonical_events, command, matcher)
"""


def _engine_bundle(agent):
    """Engine + inlined vendor config (dialect-families.md §4) for a config-driven adapter."""
    cfg = adapters.get(agent).CONFIG
    hoisted = {("json", None), ("sys", None)}

    body = []
    body.append(
        section("contract (agentseam %s)" % __version__, _strip_own_imports(_module_source("contract"), hoisted))
    )
    claims_cfg = cfg["claims"]
    if claims_cfg.get("reject_probes") or claims_cfg.get("reject_markers_unless_probe"):
        probes_source = _read(os.path.join(_ADAPTERS_DIR, "_probes.py"))
        body.append(
            section("payload probes (cited by the %s config)" % agent, _strip_own_imports(probes_source, hoisted))
        )
    if any(key in ("commandWindows", "windows") for key in cfg["hook_entry"].get("entry_extra", {})):
        windows_source = _read(os.path.join(_ADAPTERS_DIR, "_windows.py"))
        body.append(
            section("windows helper (used by the %s hook entries)" % agent, _strip_own_imports(windows_source, hoisted))
        )
    engine_source = _read(os.path.join(_ADAPTERS_DIR, "_hook_json.py"))
    body.append(section("hook_json family engine", _strip_own_imports(engine_source, hoisted)))
    entry_source = _read(os.path.join(_ADAPTERS_DIR, "_hook_entry.py"))
    body.append(section("hook-entry renderer", _strip_own_imports(entry_source, hoisted)))
    body.append(section("%s vendor config + engine binding" % agent, _BINDING.format(agent=agent, vendor=repr(cfg))))

    sections = [HEADER.format(version=__version__, agent=agent)]
    sections.append("from __future__ import annotations\n\n%s\n" % _render_imports(hoisted))
    sections.extend(body)
    sections.append(_runtime_section(agent))
    return "\n".join(sections)


def bundle(agent):
    """Render `agent`'s dispatch runtime as one self-contained, stdlib-only Python file."""
    if agent not in SUPPORTED_AGENTS:
        raise KeyError("%s: no adapter module to bundle (have: %s)" % (agent, ", ".join(SUPPORTED_AGENTS)))

    if not os.path.exists(os.path.join(_ADAPTERS_DIR, "%s.py" % agent)):
        return _engine_bundle(agent)

    adapter_source = _adapter_source(agent)
    cross = _cross_module_imports(adapter_source)

    hoisted = {("json", None), ("sys", None)}

    body = []
    body.append(
        section("contract (agentseam %s)" % __version__, _strip_own_imports(_module_source("contract"), hoisted))
    )

    for module, names in sorted(cross.items()):
        dep_source = _adapter_source(module)
        body.append(
            section("from %s (used by the %s adapter)" % (module, agent), _extract_with_deps(dep_source, names))
        )

    if _needs_windows_helper(adapter_source):
        windows_source = _read(os.path.join(_ADAPTERS_DIR, "_windows.py"))
        body.append(
            section("windows helper (used by the %s adapter)" % agent, _strip_own_imports(windows_source, hoisted))
        )

    body.append(section("%s adapter" % agent, _strip_own_imports(adapter_source, hoisted)))

    sections = [HEADER.format(version=__version__, agent=agent)]
    sections.append("from __future__ import annotations\n\n%s\n" % _render_imports(hoisted))
    sections.extend(body)
    sections.append(_runtime_section(agent))
    return "\n".join(sections)
