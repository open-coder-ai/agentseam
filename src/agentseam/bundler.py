"""Hooks, rendered standalone: bundler assembles dispatch + one adapter into one file.

Resolves the migration risk a consumer like chock names precisely: a vendored PreToolUse
runner must stay a self-contained, stdlib-only file with **no agentseam import**, because
it ships INTO an adopter repo that may never install this package at all. `bundle(agent)`
renders exactly that file -- the normalized-stdin-to-vendor-dialect plumbing this project
already owns, plus the one adapter named, with nothing left importing `agentseam`.

The composition is source-level, not a copy-paste: each section is extracted from this
package's own real modules with `ast` (stdlib), so a bundle can never drift from the
adapter it was built from -- there is only one copy of `claude_code.py`'s parse/respond
logic, and the bundler reads it, it does not re-describe it. Byte-stable for one agentseam
version: the same `(agent, __version__)` always renders the same bytes, because every
input is source text this package ships (no wall-clock, no filesystem ordering, no
environment-dependent branch) -- see `bundle()`'s own note on what that buys a consumer.

The one piece deliberately left a stub: `handle(event)`, the consumer's policy. Follows the
same scope discipline as `packaging`'s `EXECUTABLE` part (R1) -- agentseam carries the slot
and the plumbing around it; the handler BODY is never agentseam's to write. It is fenced
between marker comments (the same convention `install.py` uses for a block it owns in
someone else's file) so a consumer's own tooling can find and replace it reliably.
"""

from __future__ import annotations

import ast
import os

from . import __version__, adapters
from .allow_semantics import VOUCH_SPEAKS
from .bundler_templates import HEADER, RUNTIME, section
from .contract import EVENTS
from .matrix import capability

__all__ = ["bundle", "SUPPORTED_AGENTS"]

_HERE = os.path.dirname(__file__)
_ADAPTERS_DIR = os.path.join(_HERE, "adapters")

#: Every agent this can bundle -- exactly the agents with a real adapter module. An agent
#: with no adapter (instruction-files-only, or unadapted) has nothing here to vendor.
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
    """`source` minus `from __future__ import annotations`, every relative import, and --
    when `hoist` is given -- every module-level absolute import, collected into it instead.

    The relative ones are satisfied once, elsewhere in the bundle, by the sections this one
    is stitched after: contract's names, `_windows`'s, another adapter's.

    The absolute ones used to be left where they stood, on the reasoning that they still
    need to run there. In one file they do not: composing N sources that each legitimately
    `import json` produces N module-level imports of the same module, which every static
    analyser then reports against the consumer's repository (7 CodeQL alerts on chock's
    vendored runners, open-coder-ai/chock#73). Hoisting them into one deduplicated preamble
    is strictly safer than leaving them -- a module-level import moved earlier in the same
    module is bound before anything that could use it -- and it makes the bundle say each
    import once, which is what it means.

    Imports inside a function body are NOT touched: those are the source module's own
    decision about when to pay for an import, and rewriting a function body is more than a
    source-composer should do. `ast.parse(...).body` is module level by construction.
    """
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
    """One `import` statement per module, however many names the sources bound it to.

    A module reached under two names (`json` and `_json`) is still one import; the extra
    names become plain assignments rather than a second import of the same module, which is
    what a static analyser reads as redundant. Sorted, so the bundle stays byte-stable.
    """
    by_module = {}
    for module, asname in hoisted:
        by_module.setdefault(module, set()).add(asname)
    out = []
    for module in sorted(by_module):
        names = sorted(n for n in by_module[module] if n is not None)
        plain = None in by_module[module]
        if "." in module:  # came from `from pkg import name`
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
    """`{module: [names]}` for every `from .<module> import ...` this source makes,
    excluding `_windows` (handled by name, not folded in with a real adapter's deps)."""
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
    """The top-level defs/assignments named, plus whatever OTHER top-level names their
    bodies reference -- transitively -- so the result stands alone.

    Order follows the source file, not the request, so something is always defined before
    whatever uses it (`OBSERVED_MARKERS` before `looks_like_claude_code`, which reads it).
    """
    tree = ast.parse(source)
    owner = {}  # name -> defining node
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


def bundle(agent):
    """Render `agent`'s dispatch runtime as one self-contained, stdlib-only Python file.

    Deterministic: the same `(agent, agentseam version)` always renders identical bytes.
    Every input is source text this package ships -- no wall-clock, no filesystem
    ordering, no environment-dependent branch -- which is what lets a consumer pin the
    result byte-for-byte (chock's `VENDORED_RUNTIMES` drift check is exactly this).

    The version this was rendered from is stamped in the header, as part of those bytes --
    the only honest way to answer "is this file stale" without re-running the bundler.

    Raises KeyError for an agent with no adapter module (`SUPPORTED_AGENTS` lists what is
    bundleable).

    Everything in the result is agentseam's: normalizing stdin, degrading a decision to
    what `agent` can honor, speaking `agent`'s response dialect. The one exception is
    `handle()`, fenced between "agentseam handler" marker comments -- that is the
    consumer's policy, and this function never writes it. A caller that regenerates the
    surrounding file (a new agentseam version, a config change) can locate that block by
    its markers and carry the existing body forward, the same way `install.py` preserves
    everything outside its own marker block in a file it does not fully own.
    """
    if agent not in SUPPORTED_AGENTS:
        raise KeyError("%s: no adapter module to bundle (have: %s)" % (agent, ", ".join(SUPPORTED_AGENTS)))

    adapter_source = _adapter_source(agent)
    cross = _cross_module_imports(adapter_source)

    # Every module-level absolute import from every composed source lands here and is
    # emitted once, at the top, instead of once per source. `json` and `sys` seed it
    # because the runtime section below uses them and has no source of its own.
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

    rewrite_events = sorted(ev for ev in EVENTS if capability(agent, ev)["rewrite"])
    vouch_speaks = agent in VOUCH_SPEAKS
    note = (
        "claude_code and vscode_copilot are the only agents with real evidence that an "
        'explicit approval word means "skip confirmation"; see agentseam.allow_semantics'
        if vouch_speaks
        else "no evidence establishes that an explicit approval word means anything beyond "
        "a plain allow here, so vouch degrades to one; see agentseam.allow_semantics"
    )
    sections.append(
        section(
            "runtime (agentseam dispatch, specialized to %s)" % agent,
            RUNTIME.format(
                agent=agent,
                vouch_speaks=vouch_speaks,
                vouch_speaks_note=note,
                rewrite_events=tuple(rewrite_events),
            ),
        )
    )

    return "\n".join(sections)
