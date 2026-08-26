"""Vendor payload fixtures, captured from primary sources.

Each shape came from the vendor's own documentation, example repository, or a captured
live run -- never from a blog post. They are the asset every adapter test is built on,
so they live in one place rather than being re-typed per file.

  claude_code     live run against Claude Code 2.1.245
  cursor          vendor hook example repo (hooks.json + scripts + fixtures)
  vscode_copilot  microsoft/vscode source: memoryTool.tsx, hookCommandTypes.ts
  gemini_cli      vendor docs/hooks/reference.md
  codex_cli       vendor source: codex-rs/hooks/src/schema.rs (PreToolUseCommandInput)
"""

CC_BASH = {"hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_input": {"command": "rm -rf /"}}


CC_EDIT = {
    "hook_event_name": "PreToolUse",
    "tool_name": "Edit",
    "session_id": "s1",
    "tool_input": {"file_path": "MEMORY.md", "new_string": "fact"},
}


CC_MULTI = {
    "hook_event_name": "PreToolUse",
    "tool_name": "MultiEdit",
    "tool_input": {"file_path": "a.md", "edits": [{"new_string": "one"}, {"new_string": "two"}]},
}


CC_POST = {"hook_event_name": "PostToolUse", "tool_name": "WebFetch", "tool_use_id": "w1", "tool_output": "page text"}


CC_WRITE = {
    "hook_event_name": "PreToolUse",
    "tool_name": "Write",
    "session_id": "s1",
    "tool_use_id": "t1",
    "cwd": "/repo",
    "tool_input": {"file_path": "CLAUDE.md", "content": "team uses pnpm"},
}


CU_EDIT = {"file_path": ".cursor/rules/style.md", "edits": [{"new_string": "use named exports"}]}


CU_SHELL = {"command": "echo x >> CLAUDE.md", "cwd": "/repo"}


CX_SHELL = {
    "hook_event_name": "preToolUse",
    "session_id": "cx1",
    "turn_id": "turn-2",
    "model": "gpt-5-codex",
    "permission_mode": "auto",
    "tool_name": "shell",
    "tool_input": {"command": "rm -rf /"},
    "tool_use_id": "tu-2",
}


CX_WRITE = {
    "hook_event_name": "preToolUse",
    "session_id": "cx1",
    "turn_id": "turn-1",
    "transcript_path": "/t.json",
    "cwd": "/repo",
    "model": "gpt-5-codex",
    "permission_mode": "auto",
    "tool_name": "Write",
    "tool_input": {"file_path": "AGENTS.md", "content": "team fact"},
    "tool_use_id": "tu-1",
}


GM_AFTER = {"hook_event_name": "AfterTool", "tool_name": "write_file", "tool_output": "ok"}


GM_REPLACE = {
    "hook_event_name": "BeforeTool",
    "tool_name": "replace",
    "tool_input": {"file_path": "GEMINI.md", "new_string": "updated fact"},
}


GM_SHELL = {
    "hook_event_name": "BeforeTool",
    "tool_name": "run_shell_command",
    "tool_input": {"command": "rm -rf /"},
}


GM_WRITE = {
    "hook_event_name": "BeforeTool",
    "tool_name": "write_file",
    "session_id": "g1",
    "cwd": "/repo",
    "tool_input": {"file_path": "GEMINI.md", "content": "team prefers pnpm"},
}


VS_MEM_CREATE = {
    "tool_name": "memory",
    "session_id": "v1",
    "tool_input": {"command": "create", "path": "/memories/repo/p.md", "file_text": "pref"},
}


VS_MEM_REPLACE = {
    "tool_name": "copilot_memory",
    "tool_input": {"command": "str_replace", "path": "/memories/a.md", "old_str": "a", "new_str": "b"},
}


VS_MEM_VIEW = {"tool_name": "memory", "tool_input": {"command": "view", "path": "/memories/a.md"}}


# Windsurf: shapes from a real working installation's hook scripts
# (.windsurf/hooks/scan-run-command.sh reads .tool_info.command_line and .trajectory_id).
WS_COMMAND = {
    "hook_event_name": "pre_run_command",
    "trajectory_id": "traj-1",
    "tool_info": {"command_line": "rm -rf /"},
}
WS_PROMPT = {
    "hook_event_name": "pre_user_prompt",
    "trajectory_id": "traj-2",
    "query": "delete everything",
}
WS_POST_MCP = {
    "hook_event_name": "post_mcp_tool_use",
    "trajectory_id": "traj-3",
    "tool_info": {"server": "docs", "tool": "fetch"},
    "output": "page text",
}
