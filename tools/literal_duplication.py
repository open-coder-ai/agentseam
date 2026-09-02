"""AST survey: flags a non-docstring string literal repeated >=3x outside data/templates/tests."""

from __future__ import annotations

import ast
import os
import sys

MIN_LENGTH = 20
MIN_COUNT = 3
EXCLUDED_DIR_NAMES = frozenset({"data", "templates", "tests", "__pycache__"})


def _docstring_ids(tree):
    """id() of every Constant node that is a module/class/function's own docstring."""
    ids = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        first = node.body[0] if node.body else None
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) and isinstance(first.value.value, str):
            ids.add(id(first.value))
    return ids


def _literals_in_file(path):
    """Every non-docstring string literal >= MIN_LENGTH in `path`, with its line number."""
    tree = ast.parse(open(path, encoding="utf-8").read(), filename=path)
    docstring_ids = _docstring_ids(tree)
    return [
        (node.value, node.lineno)
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstring_ids
        and len(node.value) >= MIN_LENGTH
    ]


def _python_files(root, exclude_dirs):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in exclude_dirs)
        for name in sorted(filenames):
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def find_duplicates(root, exclude_dirs=EXCLUDED_DIR_NAMES, min_length=MIN_LENGTH, min_count=MIN_COUNT):
    """{literal: [(relative_path, lineno), ...]} for every literal repeated >= min_count times."""
    locations = {}
    for path in _python_files(root, exclude_dirs):
        for text, lineno in _literals_in_file(path):
            if len(text) >= min_length:
                locations.setdefault(text, []).append((os.path.relpath(path, root), lineno))
    return {text: locs for text, locs in locations.items() if len(locs) >= min_count}


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    root = argv[0] if argv else "src/agentseam"
    duplicates = find_duplicates(root)
    for text, locs in sorted(duplicates.items()):
        print("%dx %r" % (len(locs), text))
        for path, lineno in locs:
            print("    %s:%d" % (path, lineno))
    return 1 if duplicates else 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
