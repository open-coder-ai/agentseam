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

#: The adapter emits nothing. The vendor treats an empty exit-0 response as "no decision"
#: and continues through its own permission flow, which is exactly what ALLOW means.
ALLOW_SILENT = "silent"

#: The adapter speaks an approval, and the vendor never reads that word. Equivalent to
#: silence in effect; kept because it is what the vendor's own reference documents.
ALLOW_INERT = "inert"

#: The adapter must speak, because silence is NOT an abstention on this vendor -- it is
#: itself a decision (a block, or an approval), so there is no way to have no opinion.
ALLOW_REQUIRED = "required"

#: No evidence distinguishes silence from an explicit approval here. Left exactly as found.
ALLOW_UNVERIFIED = "unverified"

#: agent -> (kind, why). `why` is the evidence, not the restatement.
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
        "Witnessed live (Cursor 3.17.8, Windows, 2026-08-27): a beforeShellExecution hook that "
        "produced no stdout caused the tool call to be REJECTED -- the blocked command was the "
        "one trying to read the capture report, so a user watched it happen. What that does NOT "
        "settle is why, and the note recording it read the cause off the wrong half. "
        "hook_config() set failClosed:true on every permission gate at the time and the probe "
        "had no way to opt out; fail_closed arrived later. Cursor's documented default is "
        "fail-OPEN, so two readings survive: (a) an empty response is not an allow at all, or "
        "(b) an empty response is a hook ERROR, which refuses only because we asked that gate "
        "to fail closed. A sibling guardrail installs the same event with no failClosed and does "
        "not block the commands it allows, which is evidence for (b). REQUIRED either way while "
        "these gates install fail-closed by default: under (a) silence never allows, under (b) "
        "it allows only where the operator turned the gate's own protection off. Distinguishing "
        "them is a one-line live test -- a beforeShellExecution hook that does nothing but exit "
        "0, installed WITHOUT failClosed, against one shell command -- and worth running: (b) "
        "moves this row to SILENT and makes Cursor consistent with everything else here.",
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
