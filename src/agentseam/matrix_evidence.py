"""How each matrix row's claims were established, kept apart from the claims themselves.

Two different activities. A row's `events` table says what an agent can do; its evidence
says how anyone knows. The second is what an adopter should read first -- `basis` names the
kind of evidence in a closed vocabulary, and most rows here are `vendor-docs`, which is a
claim about what a vendor says rather than an observation of what their build does.

Separating them makes the honest shape of this project visible in one file: one row rests on
a live run.
"""

from __future__ import annotations

from .matrix_terms import BASIS_DOCS, BASIS_LIVE, BASIS_SOURCE, BASIS_THIRD_PARTY

EVIDENCE = {
    "antigravity": {
        "basis": BASIS_DOCS,
        "version": "2.0 / CLI",
        "date": "2026-08-26",
        "method": "vendor hooks documentation read directly (per-event schemas and decision vocabulary)",
    },
    "claude_code": {
        "basis": BASIS_LIVE,
        "version": "2.1.245",
        "date": "2026-08-25",
        "method": "live headless run + official hooks reference",
    },
    "codex_cli": {
        "basis": BASIS_SOURCE,
        "version": "source @ main 2026-08-26",
        "date": "2026-08-26",
        "method": "vendor source: codex-rs/hooks/src/schema.rs, engine/output_parser.rs, HookEventName.ts",
    },
    "cursor": {
        "basis": BASIS_DOCS,
        "version": "1.7+",
        "date": "2026-08-26",
        "method": "vendor hooks documentation read directly (event list, per-event schemas, exit codes)",
    },
    "devin": {
        "basis": BASIS_DOCS,
        "version": "CLI",
        "date": "2026-08-26",
        "method": "vendor hooks documentation read directly (events, output format, exit codes)",
    },
    "gemini_cli": {
        "basis": BASIS_DOCS,
        "version": "docs @ main 2026-08-26",
        "date": "2026-08-26",
        "method": "vendor hooks reference (docs/hooks/reference.md in google-gemini/gemini-cli), read from a clone",
    },
    "grok": {
        "basis": BASIS_DOCS,
        "version": "CLI",
        "date": "2026-08-26",
        "method": "vendor hooks documentation read directly (events, script contract, exit codes)",
    },
    "junie": {
        "basis": BASIS_DOCS,
        "version": "EAP",
        "date": "2026-08-26",
        "method": "vendor hooks documentation read directly (events, decisions, config merging, limitations)",
    },
    "kimi_code": {
        "basis": BASIS_DOCS,
        "version": "CLI",
        "date": "2026-08-26",
        "method": "vendor hooks documentation read directly (event table, return values, config fields)",
    },
    "tabnine": {
        "basis": BASIS_DOCS,
        "version": "CLI",
        "date": "2026-08-26",
        "method": "vendor hooks documentation read directly (event table, exit codes, output fields)",
    },
    "vscode_copilot": {
        "basis": BASIS_SOURCE,
        "version": "1.110+",
        "date": "2026-08-26",
        "method": "microsoft/vscode source: languageModelToolsService.invokeTool + hookCommandTypes",
    },
    "windsurf": {
        "basis": BASIS_THIRD_PARTY,
        "version": "hooks.json schema as shipped 2026-08",
        "date": "2026-08-26",
        "method": "a real working installation (.windsurf/hooks.json + hook scripts) in "
        "PaloAltoNetworks/prisma-airs-integrations; vendor docs unreachable from this network",
    },
    "aider": {
        "basis": BASIS_DOCS,
        "version": "2026-08",
        "date": "2026-08-26",
        "method": "docs/config reference",
    },
    "replit": {
        "basis": BASIS_DOCS,
        "version": "n/a",
        "date": "2026-08-26",
        "method": "looked for a hooks surface in the vendor's documentation and did not find one; "
        "recorded as not-found rather than as absent, since a hosted agent may expose one elsewhere",
    },
    "zed": {
        "basis": BASIS_DOCS,
        "version": "2026-08",
        "date": "2026-08-26",
        "method": "docs + open extensibility issues",
    },
}
