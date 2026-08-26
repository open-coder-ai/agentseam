"""The payloads the generated examples are built from -- one per adapted agent.

Each is the same situation in that vendor's own dialect: **the agent is about to write a
secret into a file it will read back later.** Holding the situation constant is what makes
the generated pages comparable; the differences you see between them are entirely the
vendors' own.

The secret is a self-evident placeholder rather than a realistic-looking key. A repository
full of strings that pattern-match as credentials teaches secret scanners to cry wolf, and
this project's own CI runs two of them.

These are hand-written from vendor documentation rather than imported from the test suite,
because an example that only proves the tests agree with themselves proves nothing. A test
does check one thing about them: that each payload is claimed by exactly the agent it
claims to be, so a page can never describe the wrong agent's behaviour.
"""

from __future__ import annotations

#: agent -> a pre-tool payload in that agent's dialect.
SCENARIOS = {
    "claude_code": {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "CLAUDE.md", "content": "AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY"},
        "session_id": "example",
        "cwd": "/repo",
    },
    "codex_cli": {
        "hook_event_name": "preToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "AGENTS.md", "content": "AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY"},
        "session_id": "example",
        "turn_id": "turn-1",
        "permission_mode": "auto",
        "model": "gpt-5-codex",
        "cwd": "/repo",
    },
    "cursor": {
        "hook_event_name": "preToolUse",
        "tool_name": "Write",
        "tool_input": {
            "file_path": ".cursor/rules/team.md",
            "content": "AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY",
        },
        "conversation_id": "example",
        "generation_id": "gen-1",
        "cursor_version": "1.7.2",
        "model": "claude-opus-4-7-thinking-max",
        "workspace_roots": ["/repo"],
        "cwd": "/repo",
    },
    "devin": {
        "hook_event_name": "PreToolUse",
        "tool_name": "write_file",
        "tool_input": {"file_path": "AGENTS.md", "content": "AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY"},
        "session_id": "example",
        "prompt_id": "turn-1",
    },
    "gemini_cli": {
        "hook_event_name": "BeforeTool",
        "tool_name": "write_file",
        "tool_input": {"file_path": "GEMINI.md", "content": "AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY"},
        "session_id": "example",
        "cwd": "/repo",
    },
    "grok": {
        "hookEventName": "PreToolUse",
        "toolName": "Write",
        "toolInput": {"file_path": "AGENTS.md", "content": "AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY"},
        "sessionId": "example",
        "workspaceRoot": "/repo",
    },
    "kimi_code": {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "AGENTS.md", "content": "AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY"},
        "client_type": "kimi_code_cli",
        "session_id": "example",
        "cwd": "/repo",
    },
    "antigravity": {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "AGENTS.md", "CodeContent": "AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY"},
        },
        "stepIdx": 3,
        "conversationId": "example",
        "workspacePaths": ["/repo"],
        "modelName": "gemini-3.6-flash-medium",
    },
    "vscode_copilot": {
        "tool_name": "memory",
        "tool_input": {
            "command": "create",
            "path": "/memories/repo/team.md",
            "file_text": "AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY",
        },
        "session_id": "example",
    },
    # Windsurf has no file-write event at all, so the closest thing it can see is the
    # shell command that would do the writing. That gap is the point of its page.
    "windsurf": {
        "hook_event_name": "pre_run_command",
        "trajectory_id": "example",
        "tool_info": {"command_line": "echo 'AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY' >> AGENTS.md"},
    },
}
