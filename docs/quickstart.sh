#!/usr/bin/env bash
set -euo pipefail
# Generated from README.md's "Quick start" block by tools/quickstart_block.py.
# Do not edit by hand -- edit the README and regenerate.

mkdir demo && cd demo && git init -q
cat > my_handler.py << 'EOF'
from agentseam import run, Decision

def handler(event):
    if event.event == "pre_tool" and "AKIA" in (event.content or ""):
        return Decision.deny("no AWS keys in memory files")
    return Decision.allow()

run(handler)
EOF
pip install agentseam
agentseam install all "python3 my_handler.py" --events pre_tool --repo .
