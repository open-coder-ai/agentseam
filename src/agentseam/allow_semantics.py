"""What a bare ALLOW means to each vendor, kept apart from the adapters that act on it.

A handler returning ALLOW has said one thing -- "I have no objection" -- and adapters were
spelling it two ways, six silent and six speaking an explicit approval, with nothing
recording which was deliberate. That split was not a style difference. On VS Code Copilot
and Claude Code the explicit word is read as *skip the user's confirmation*, so a policy
that simply did not match -- the common case, on every tool call -- was disabling the user's
own protection for the whole session. That was fixed on those two; this file is the audit of
the other ten, so the next reader can see the answer instead of re-deriving it.

The rule the table encodes: **a bare ALLOW must land on whatever the vendor would have done
with no hook at all.** Usually that is silence. It is not always available -- on Cursor an
empty response was witnessed to REJECT the call, so abstaining is not something a hook there
can do -- and where it is not, the adapter must speak, and the reason is recorded here
rather than left to look like an oversight.

`UNVERIFIED` is a real answer and deliberately not resolved by picking the safer-sounding
option. Silencing a vendor whose empty response blocks would turn every allow into a denial;
speaking to one that reads the word as auto-approve is the defect above. Both directions are
guesses, and this project does not guess vendor shapes -- it records the gap and waits for a
session that can settle it.
"""

from __future__ import annotations

ALLOW_SILENT = "silent"

ALLOW_INERT = "inert"

ALLOW_REQUIRED = "required"

ALLOW_UNVERIFIED = "unverified"

ALLOW_SEMANTICS = {
    "claude_code": (
        ALLOW_SILENT,
        'Documented verbatim: "Exit code 0 with no output means the hook has no decision to '
        'report, so the tool call continues through the normal permission flow." What an '
        "explicit allow does there is NOT documented, and its sibling product reads the same "
        "word as auto-approve, so the recorded option is the one that keeps the user's prompt.",
    ),
    "vscode_copilot": (
        ALLOW_SILENT,
        "Source, not inference: languageModelToolsService returns `autoConfirmed: "
        '{ConfirmKind.ConfirmationNotNeeded, "Allowed by hook"}` on permissionDecision:"allow", '
        "so the explicit word skips the confirmation the user would otherwise have seen.",
    ),
    "codex_cli": (
        ALLOW_SILENT,
        "Source: output_parser.rs's `unsupported_pre_tool_use_hook_specific_output` REJECTS "
        "permissionDecision:allow unless it carries updatedInput, and a rejected response is a "
        "hook error, which fails open. Silence is the only spelling of allow Codex accepts at "
        "every event.",
    ),
    "grok": (
        ALLOW_SILENT,
        "There is no allow verb to speak: the vocabulary is {decision: deny, reason} and "
        "nothing more, and exit 0 is how a hook says it has no objection.",
    ),
    "windsurf": (
        ALLOW_SILENT,
        "Exit-code-only protocol -- 2 blocks a pre_* hook and everything else allows. stdout "
        "carries no decision, so there is no word to say.",
    ),
    "kimi_code": (
        ALLOW_SILENT,
        "Takes Claude Code's hookSpecificOutput shape, where an absent decision is no decision, "
        "and fails open besides: exactly three events block and the rest are fire-and-forget.",
    ),
    "gemini_cli": (
        ALLOW_INERT,
        "Source (google-gemini/gemini-cli @ main, read from a clone 2026-08-28): nothing in the "
        "tree tests for 'allow'. Only isBlockingDecision() (block|deny) and isAskDecision() "
        "(ask) are ever consulted, and hookAggregator SYNTHESISES decision:'allow' itself when "
        "no hook blocked or asked. The word cannot skip a confirmation here the way VS Code's "
        "can, so the documented reply is kept.",
    ),
    "cursor": (
        ALLOW_REQUIRED,
        "SETTLED by a two-trial live experiment (Cursor 3.17.8, Windows, 2026-08-28). One "
        "beforeShellExecution hook that read stdin, logged, and exited 0 in silence, run "
        "against `echo hello`, with one key differing between trials: without failClosed the "
        "command RAN; with failClosed:true it was BLOCKED. So silence here is neither a "
        "refusal nor an abstention -- it is a hook ERROR. Fail-open ignores it, fail-closed "
        "refuses on it. That retires the two readings this row carried, and the #23 note's "
        "flat 'silence blocks' with them: it was true only because hook_config() set "
        "failClosed on every gate with no way to opt out. REQUIRED, and now for a proven "
        "reason rather than a hedged one -- agentseam installs these gates fail-closed by "
        "DEFAULT, so an adapter that went silent here would block every allowed tool call on "
        "the vendor's strongest posture. See tests/test_fail_closed_gates_are_answered.py; "
        "the same run also showed the hook firing TWICE per command (sandbox:true, then "
        "sandbox:false on Cursor's retry).",
    ),
    "junie": (
        ALLOW_REQUIRED,
        "Documented: at PermissionRequest a hook that exits 0 without a blocking decision "
        "APPROVES the action and skips the dialog the user would otherwise have seen. Silence "
        "is therefore a decision too, and the same respond() branch serves PreToolUse, so there "
        "is no spelling of abstention available at either.",
    ),
    "antigravity": (
        ALLOW_UNVERIFIED,
        "Docs-basis only, and the docs settle neither half: they give PreToolUse's vocabulary "
        "(allow, deny, ask, force_ask, deny_unless_prior_grant) without saying what `allow` does "
        "to a pending confirmation, and say nothing about an empty response. The fail mode is "
        "undocumented too. Needs a live session.",
    ),
    "devin": (
        ALLOW_UNVERIFIED,
        "Docs-basis only. The vocabulary is approve/block with no ask, and non-zero exits other "
        "than 2 are logged without blocking -- but nothing records what an empty exit-0 response "
        "does, nor whether `approve` bypasses anything, since Devin's own permission flow is not "
        "described here. Needs a live session.",
    ),
    "tabnine": (
        ALLOW_UNVERIFIED,
        "Docs-basis only. Silence is probably harmless -- stdout that is not valid JSON is "
        "treated as a systemMessage and the action allowed, and an empty string is not valid "
        "JSON -- but 'the action is allowed' is the same phrase the docs use for an explicit "
        "allow, so the two are not distinguished and the distinction is the whole question.",
    ),
}

VOUCH_SPEAKS = frozenset({"claude_code", "vscode_copilot"})
