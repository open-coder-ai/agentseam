"""AST-read: the ordered field-fallback chains inside each adapter's `parse()`.

Most of the 12 adapters write `parse()` as `ti.get("a") or ti.get("b") or ...` chains off
exactly two local names -- `ti` (the decoded `tool_input`) and `raw` (the payload) -- so one
generic AST walker recovers the ordered chain for all of them. The three vendors whose
`parse()` does not fit that shape (vscode_copilot's memory/non-memory branch, windsurf's
`tool_info` sub-object, antigravity's PascalCase argument loop) get a small, cited override
each instead of a bigger, more fragile generic walker.
"""

from __future__ import annotations

import ast
import inspect

FIELD_NAMES = ("tool", "command", "path", "content", "output", "prompt", "session_id", "cwd", "tool_use_id")

#: Synthetic key appended to a `fields` chain when `parse()` falls back to joining an
#: `edits` list's `new_string` entries (claude_code.py:96-98, kimi_code.py, junie.py alike).
EDITS_JOIN_SENTINEL = "tool_input.edits[].new_string"

#: The only two local names a `.get()` chain is read off in the 9 marker/flat_decision
#: adapters -- `ti` is always the decoded `tool_input`, `raw` is the payload itself.
_CHAIN_ROOTS = {"ti": "tool_input", "raw": ""}


def _key_of(node):
    """`X.get("k")` for a root `X` in `_CHAIN_ROOTS` -> `"tool_input.k"` / `"k"`; else None."""
    if (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "get"
        and node.args
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id in _CHAIN_ROOTS
    ):
        key_node = node.args[0]
        if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
            prefix = _CHAIN_ROOTS[node.func.value.id]
            return "%s.%s" % (prefix, key_node.value) if prefix else key_node.value
    return None


def _or_terms(node):
    if isinstance(node, ast.BoolOp) and isinstance(node.op, ast.Or):
        terms = []
        for value in node.values:
            terms.extend(_or_terms(value))
        return terms
    return [node]


def _resolve_chain(node, assigns, seen=frozenset()):
    keys = []
    for leaf in _or_terms(node):
        if isinstance(leaf, ast.Constant) and leaf.value is None:
            continue
        key = _key_of(leaf)
        if key is not None:
            keys.append(key)
        elif isinstance(leaf, ast.Name) and leaf.id in assigns and leaf.id not in seen:
            keys.extend(_resolve_chain(assigns[leaf.id], assigns, seen | {leaf.id}))
    return keys


def _is_isinstance_list(node):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "isinstance"
        and len(node.args) == 2
        and isinstance(node.args[0], ast.Call)
    )


def _analyze_parse(fn):
    """First-assignment-per-name, the kwargs of the `Event(...)` call, and edits-guarded names."""
    tree = ast.parse(inspect.getsource(fn))
    assigns, event_kwargs, edits_guarded = {}, {}, set()

    def walk(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.Assign) and len(child.targets) == 1 and isinstance(child.targets[0], ast.Name):
                assigns.setdefault(child.targets[0].id, child.value)
            if isinstance(child, ast.If) and isinstance(child.test, ast.BoolOp) and isinstance(child.test.op, ast.And):
                clauses = child.test.values
                if any(_key_of(c.args[0]) == "tool_input.edits" for c in clauses if _is_isinstance_list(c)):
                    for clause in clauses:
                        if isinstance(clause, ast.Compare) and isinstance(clause.left, ast.Name):
                            edits_guarded.add(clause.left.id)
            if isinstance(child, ast.Call) and isinstance(child.func, ast.Name) and child.func.id == "Event":
                for kw in child.keywords:
                    event_kwargs.setdefault(kw.arg, kw.value)
            walk(child)

    walk(tree.body[0])
    return assigns, event_kwargs, edits_guarded


def _generic_fields(mod):
    """The `fields` chains for the 9 adapters whose `parse()` is `ti.get(...) or ...` chains."""
    assigns, event_kwargs, edits_guarded = _analyze_parse(mod.parse)
    result = {}
    for name in FIELD_NAMES:
        node = event_kwargs.get(name)
        if node is None:
            continue
        chain = _resolve_chain(node, assigns)
        guarded_name = node.id if isinstance(node, ast.Name) else None
        if guarded_name is None and isinstance(node, ast.BoolOp):
            for leaf in _or_terms(node):
                if isinstance(leaf, ast.Name) and leaf.id in edits_guarded:
                    guarded_name = leaf.id
        if guarded_name in edits_guarded:
            chain.append(EDITS_JOIN_SENTINEL)
        if chain:
            result[name] = chain
    return result


def _fields_vscode_copilot(mod):
    """Bespoke: `parse()` branches on `tool in MEMORY_TOOLS` (vscode_copilot.py:66-83) --
    two disjoint field sets the generic `ti.get(...) or ...` walker cannot pick apart because
    both live under the same `Event(path=path, content=content, ...)` call site."""
    return {
        "fields": {
            "tool": ["tool_name", "toolName"],
            "path": ["tool_input.filePath", "tool_input.file_path", "tool_input.path"],
            "content": ["tool_input.content", "tool_input.newText", "tool_input.new_str"],
            "command": ["tool_input.command"],
            "output": ["tool_output", "tool_response"],
            "prompt": ["prompt"],
            "session_id": ["session_id"],
            "cwd": ["cwd"],
            "tool_use_id": ["tool_use_id"],
        },
        "fields_memory_write": {
            "path": ["tool_input.path"],
            "content": ["tool_input.file_text", "tool_input.new_str", "tool_input.insert_text"],
        },
    }


def _fields_windsurf(mod):
    """Bespoke: keys live on `tool_info` (local var `info`, windsurf.py:37-56), a root the
    generic walker does not know, and `tool` is built from an if/else, not an `or` chain."""
    return {
        "fields": {
            "command": ["tool_info.command_line"],
            "path": ["path", "tool_info.path"],
            "output": ["output", "result"],
            "prompt": ["query", "prompt"],
            "session_id": ["trajectory_id"],
            "cwd": ["cwd"],
        }
    }


def _fields_antigravity(mod):
    """Bespoke: no `.get()` chains at all -- PascalCase argument names are tried in a `for`
    loop over module constants (antigravity.py:16-31,45-67), read directly here."""
    path_args = ["toolCall.args.%s" % key for key in mod._PATH_ARGS]
    content_args = ["toolCall.args.%s" % key for key in mod._CONTENT_ARGS] + [
        "toolCall.args.ReplacementChunks[].ReplacementContent"
    ]
    return {
        "fields": {
            "tool": ["toolCall.name"],
            "command": ["toolCall.args.%s" % mod._COMMAND_ARG],
            "path": path_args,
            "content": content_args,
            "output": ["error"],
            "session_id": ["conversationId"],
            "tool_use_id": ["stepIdx"],
            "cwd": ["toolCall.args.Cwd", "workspacePaths[0]"],
        }
    }


_OVERRIDE = {
    "vscode_copilot": _fields_vscode_copilot,
    "windsurf": _fields_windsurf,
    "antigravity": _fields_antigravity,
}


def fields(agent, mod):
    if hasattr(mod, "CONFIG"):
        # Config-driven adapter: the chains ARE its parse() (the engine executes them), so
        # there is no second source to derive from; behaviour is held by the golden fixtures
        # and the per-adapter suites.
        out = {"fields": {name: list(chain) for name, chain in mod.CONFIG["fields"].items()}}
        if "fields_memory_write" in mod.CONFIG:
            out["fields_memory_write"] = {k: list(v) for k, v in mod.CONFIG["fields_memory_write"].items()}
        return out
    if agent in _OVERRIDE:
        return _OVERRIDE[agent](mod)
    return {"fields": _generic_fields(mod)}
