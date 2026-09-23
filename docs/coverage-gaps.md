# Coverage gaps only a real agent can close

The probe (`agentseam probe`, promoted from `tools/experiment.py` in wave 1 of the `armed`
initiative) covers 8 trials × 3 gateable events × 16 agents. Witnessed evidence now covers
`claude_code@2.1.275` at **all three gates and all eight trials**, including `escalate` (the
one `PreToolUse` reading no vendor doc settles) -- see
`data/recordings/claude_code@2.1.275.json`. The three gaps this file was written for are
closed for `claude_code`; `cursor@3.21.18` is witnessed at two of them (`pre_tool` and
`stop`) -- see the `verified` record in `data/matrix.json`. Every other agent's are open, and
the procedure below is how you close one.

Closing them needs a machine where the vendor's own client is installed and authenticated.
That is usually not a cloud session, but the constraint is the credential, not the cloud: a
container with a working client can witness.

## What "witnessed", "tested" and "recorded" mean

A reader must be able to tell these apart without opening the source:

| Word | What it means | How you get one |
| :--- | :--- | :--- |
| **witnessed** | Somebody watched the real vendor client do this, on this machine, right now. | `--driver harness`, or your own headless CLI with a bare `{prompt}` |
| **tested** | An automated check exercised the code path -- the dialect, the classifier, the schema -- without a real vendor client. Real, useful, **not** a vendor observation. | `--driver reference` (the protocol made executable) or the `pytest` suite itself |
| **recorded** | A previously *witnessed* run, frozen to a file and replayed deterministically. The data is witnessed; the replay is not a new witness. | `--driver recorded` (the default once a recording exists) |

`agentseam probe run`'s own output never blurs these: a report's `driver` field is one of
`real-agent`, `reference` or `recorded`, and its `basis` field is one of `live-run`,
`live-run-partial`, `vendor-docs`, `vendor-source`, `third-party-install` or `inherited`
(`src/agentseam/matrix_terms.py`). `evidence_report.validate()` refuses a report from the
`reference` driver that claims a live basis -- that is the one invariant this whole
initiative exists to enforce (contract invariant 1).

## Where the gaps are now

`claude_code` is witnessed at all three gates at `2.1.275`. What remains open:

1. **Every other agent, at every gate.** Fourteen of the sixteen have never been witnessed.
   `cursor` is witnessed at `pre_tool` (a `{permission: deny}` on a `Write` was honoured and
   the file never landed) and at `stop` (a `{followup_message}` re-ran the agent, and a silent
   hook let the turn end, so `stop` fails open); its `prompt_submit` gate is still open.
2. **`claude_code` on a platform other than `linux`.** A recording carries its `platform`.
3. **Each new `claude_code` build.** `tools/watch_versions.py` is what notices a ship; a
   recording is only evidence for the version it names.

## Close one gap

**Prefer `--driver harness`.** For any agent `agentseam.harness` knows, it supplies that
vendor's own headless invocation, already correct, and there is nothing to quote:

```bash
agentseam probe run --agent claude_code --event pre_tool \
    --driver harness \
    --agent-version <version> --record --report --reporter @yourhandle \
    > pre_tool-report.json
```

Repeat with `--event prompt_submit` and `--event stop`. For an agent the registry does not
know, write the template yourself -- and **leave `{prompt}` bare**:

```bash
    --driver 'my-agent -p {prompt} --whatever-flag'     # correct
    --driver 'my-agent -p "{prompt}"'                   # refused, see below
```

The substitution supplies the quotes itself. Quoting the slot as well ends the quote early,
which hands the trigger's own `>>` to the shell as a redirect: the driver's chat output is
appended to the sentinel file, the run counts those lines as the action having run, and a
trial the agent actually *refused* is recorded as `allow`. That is a false witnessed row
produced by following this file, so `drive_real` now refuses a quoted slot outright rather
than letting the run proceed.

`--record` appends to (never replaces) `data/recordings/claude_code@<version>.json`, so
running all three builds one recording covering every gate. `--report` prints the
evidence-report shape alongside it -- the two are independent flags and combine safely; the
`.json` files above are what you paste into the **Evidence report** issue template, or add
directly to a PR (`data/recordings/*.json` plus the `data/matrix.json` per-claim `test`
pointers the recording backs).

`docs/witness-skeleton.json`'s `report` blocks are placeholders on purpose: replace the
blank fields with your actual `--report` output, never hand-type a `basis`, `date` or
`version`. `tests/test_coverage_skeleton.py` asserts the committed skeleton fails
`evidence_report.validate()` exactly as it stands, and a genuinely filled-in block
validates -- so the file can never be mistaken for evidence, only for the shape evidence
takes.

## What this is not

A run against `reference` or `recorded` never counts as closing one of these gaps -- only a
run against the real, installed `claude_code` does. See
[CONTRIBUTING.md](../CONTRIBUTING.md#contributing-evidence-you-do-not-need-to-write-code)
for the full walk-through and the two ways to submit what you find.
