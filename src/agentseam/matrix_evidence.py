"""How each matrix row's claims were established, kept apart from the claims themselves.

Two different activities. A row's `events` table says what an agent can do; its evidence
says how anyone knows. The second is what an adopter should read first -- `basis` names the
kind of evidence in a closed vocabulary, and most rows here are `vendor-docs`, which is a
claim about what a vendor says rather than an observation of what their build does.

Separating them makes the honest shape of this project visible in one file: three rows rest
on a live run, and only one of those saw every event it claims. Each live round has corrected
something source or docs had been read wrongly, which is the argument for running more.
"""

from __future__ import annotations

from .matrix_terms import BASIS_DOCS, BASIS_LIVE, BASIS_LIVE_PARTIAL, BASIS_SOURCE, BASIS_THIRD_PARTY

EVIDENCE = {
    "antigravity": {
        "basis": BASIS_DOCS,
        "version": "2.0 / CLI",
        "date": "2026-08-26",
        "method": "vendor hooks documentation read directly (per-event schemas and decision vocabulary)",
    },
    "claude_code": {
        "basis": BASIS_LIVE,
        "version": "2.1.247",
        "date": "2026-08-28",
        "method": (
            "live headless run (2.1.245) for the payload shapes, plus a live response-contract "
            "experiment on Windows (2.1.247, 2026-08-28) for what each event actually READS: "
            "one candidate reply shape per trial, with the verdict taken from the agent's own "
            "behaviour rather than the hook's claim -- a marker file the trial prompt asked "
            "for at UserPromptSubmit, and the Stop hook re-firing with stop_hook_active at "
            'Stop. That run established {"decision": "block"} and exit 2 as honoured at '
            "both, and hookSpecificOutput.permissionDecision -- the shape this adapter had "
            "always emitted there -- as ignored at both. The official hooks reference could "
            "not settle it: two reads of the same page disagreed, and one said those events "
            "had no JSON decision control at all. pre_tool was checked in the same round and does "
            "honour permissionDecision, so the three blocking events this row claims are now "
            "each backed by an observation rather than by inference from the other two."
        ),
        # Canonical events whose RESPONSE contract was verified in that round. pre_tool is
        # included: permissionDecision blocked a Write there outright, and the agent's next
        # Bash call too, so it is established rather than inherited from documentation.
        "observed": ("pre_tool", "prompt_submit", "stop"),
    },
    "codex_cli": {
        "basis": BASIS_LIVE_PARTIAL,
        "version": "0.150.1",
        "date": "2026-08-28",
        "method": (
            "vendor source (codex-rs: config/src/hook_config.rs, hooks/src/schema.rs, "
            "engine/output_parser.rs, engine/discovery.rs), plus a live capture on Windows: "
            "74 real payloads across two sessions, every one claimed by this adapter. That "
            "run is what corrected the event-name casing, the write-tool vocabulary and the "
            "per-event response dialects -- each of which source alone had been read wrongly. "
            "`observed` lists the events actually seen fire; the rest of this row still rests "
            "on source. HookEventName.ts is deliberately no longer cited: it is a ts-rs "
            "binding for the App Server's IDE-facing protocol, not the CLI hook dialect this "
            "adapter speaks, and citing it is what put camelCase event names here."
        ),
        # Canonical events seen against the running agent -- NOT a claim about the four this
        # row also asserts (pre_compact, session_end, subagent_start, subagent_stop), which
        # simply did not fire in either session.
        "observed": (
            "post_tool",
            "pre_tool",
            "prompt_submit",
            "session_start",
            "stop",
        ),
    },
    "cursor": {
        "basis": BASIS_LIVE_PARTIAL,
        "version": "3.17.8",
        "date": "2026-08-27",
        "method": (
            "vendor hooks documentation, plus a live capture on Windows: 120 real payloads "
            "across four sessions, every one claimed by this adapter and none carrying a "
            "vendor event we do not map. `observed` lists the events actually seen fire; the "
            "rest of this row still rests on documentation."
        ),
        # Canonical events seen against the running agent. Deliberately NOT a claim about the
        # five this row also asserts -- see NOTES for what three sessions failed to observe.
        "observed": (
            "file_changed",
            "post_tool",
            "pre_tool",
            "prompt_submit",
            "session_start",
            "stop",
        ),
    },
    "devin": {
        "basis": BASIS_DOCS,
        "version": "CLI",
        "date": "2026-08-26",
        "method": "vendor hooks documentation read directly (events, output format, exit codes)",
    },
    "gemini_cli": {
        "basis": BASIS_SOURCE,
        "version": "source @ main 2026-08-28",
        "date": "2026-08-28",
        "method": (
            "google-gemini/gemini-cli source, read from a clone rather than only from the "
            "hooks reference: hooks/types.ts (isBlockingDecision/isAskDecision -- the only "
            "predicates any consumer calls), hooks/hookAggregator.ts (which SYNTHESISES "
            "decision:'allow' when no hook objected), scheduler/hook-utils.ts and "
            "scheduler/scheduler.ts (where a BeforeTool verdict becomes PolicyDecision and "
            "then a forced confirmation), and core/client.ts (BeforeAgent/AfterAgent, which "
            "consult only isBlockingDecision). That reading corrected the reference on two "
            "points at once: `ask` is honoured at BeforeTool and this adapter was denying "
            "instead, and `allow` is read nowhere at all."
        ),
        # Not a live run: no event here has been seen fire against a running Gemini CLI.
        # This row says what the code does with a reply, not that a reply was ever sent.
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
        "date": "2026-08-28",
        "method": (
            "microsoft/vscode source, read from a clone rather than from the docs: "
            "hookTypes.ts (HOOKS_BY_TARGET -- both products' event-name maps), "
            "hookSchema.ts and hookCompatibility.ts (parseCopilotHooks, the config shape "
            "actually parsed), hookCommandTypes.ts and chatHookService.ts (per-event input "
            "and output contracts, exit-code semantics), hookResultProcessor.ts, and "
            "languageModelToolsService.ts (where the decision is honoured). That reading "
            "corrected the event vocabulary, the installed config shape, the fail mode and "
            "the response dialects -- every one of which had been wrong. No live run: "
            "`observed` is absent here on purpose."
        ),
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
