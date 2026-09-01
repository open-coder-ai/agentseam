"""The ordered field-fallback chains each entry's `parse()` runs.

Eleven adapters are config-driven, so their chains ARE their `parse()` (the engine
executes them) and are echoed back from the entry itself; behaviour is held by the golden
fixtures and the per-adapter suites. vscode_copilot -- the one dialect module left -- keeps
a small, cited override: its `parse()` branches on `tool in MEMORY_TOOLS`
(vscode_copilot.py:66-83), two disjoint field sets no chain walker could pick apart.
"""

from __future__ import annotations


def _fields_vscode_copilot(mod):
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


_OVERRIDE = {"vscode_copilot": _fields_vscode_copilot}


def fields(agent, mod):
    if hasattr(mod, "CONFIG"):
        out = {
            "fields": {
                name: list(chain) if isinstance(chain, (list, tuple)) else chain
                for name, chain in mod.CONFIG["fields"].items()
            }
        }
        if "fields_memory_write" in mod.CONFIG:
            out["fields_memory_write"] = {k: list(v) for k, v in mod.CONFIG["fields_memory_write"].items()}
        return out
    return _OVERRIDE[agent](mod)
