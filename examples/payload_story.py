"""The story every example payload tells, held constant so the per-agent pages compare."""

from __future__ import annotations

#: Self-evident placeholder. A repository full of strings that pattern-match as credentials
#: teaches secret scanners to cry wolf, and this project's CI runs two of them.
SECRET = "AWS_SECRET_ACCESS_KEY=EXAMPLE-PLACEHOLDER-NOT-A-KEY"
MEMORY_FILE = "AGENTS.md"
PROMPT = "remember my aws key so you can deploy later"
FAILING = "npm test"
FAILURE = "1 test failed"
