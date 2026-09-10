# Coverage gaps only a real agent can close

The probe (`agentseam probe`, promoted from `tools/experiment.py` in wave 1 of the `armed`
initiative) covers 8 trials × 3 gateable events × 16 agents. The witnessed evidence covers a
narrow slice of that: `claude_code@2.1.263`, `pre_tool` only, and every trial except
`escalate` (the one `PreToolUse` reading no vendor doc settles). This closes the *tooling*
gap, not the *evidence* gap -- **a cloud session holds no vendor credentials and cannot
produce a witnessed row.** These three gaps are yours to close, on a machine with Claude
Code installed and authenticated.

## What "witnessed", "tested" and "recorded" mean

A reader must be able to tell these apart without opening the source:

| Word | What it means | How you get one |
| :--- | :--- | :--- |
| **witnessed** | Somebody watched the real vendor client do this, on this machine, right now. | `--driver "<your headless CLI, containing {prompt}>"` |
| **tested** | An automated check exercised the code path -- the dialect, the classifier, the schema -- without a real vendor client. Real, useful, **not** a vendor observation. | `--driver reference` (the protocol made executable) or the `pytest` suite itself |
| **recorded** | A previously *witnessed* run, frozen to a file and replayed deterministically. The data is witnessed; the replay is not a new witness. | `--driver recorded` (the default once a recording exists) |

`agentseam probe run`'s own output never blurs these: a report's `driver` field is one of
`real-agent`, `reference` or `recorded`, and its `basis` field is one of `live-run`,
`live-run-partial`, `vendor-docs`, `vendor-source`, `third-party-install` or `inherited`
(`src/agentseam/matrix_terms.py`). `evidence_report.validate()` refuses a report from the
`reference` driver that claims a live basis -- that is the one invariant this whole
initiative exists to enforce (contract invariant 1).

## The three gaps

1. **`escalate` at `pre_tool`.** The recording covers seven of eight trials at this gate.
2. **Every trial at `prompt_submit`.** No agent has ever been witnessed at this gate.
3. **Every trial at `stop`.** No agent has ever been witnessed at this gate, including the
   sentinel re-fire asymmetry that gate's own docs describe
   (`src/agentseam/probe/experiment.py`'s `_blocked()`).

## Close one gap

Pick a row from [`docs/witness-skeleton.json`](witness-skeleton.json) and run its command,
replacing the placeholder driver with your own headless invocation:

```bash
agentseam probe run --agent claude_code --event pre_tool --trial escalate \
    --driver "<your headless claude_code invocation, containing {prompt}>" \
    --agent-version <version> --record --report --reporter @yourhandle \
    > escalate-pre_tool-report.json

agentseam probe run --agent claude_code --event prompt_submit \
    --driver "<your headless claude_code invocation, containing {prompt}>" \
    --agent-version <version> --record --report --reporter @yourhandle \
    > prompt_submit-report.json

agentseam probe run --agent claude_code --event stop \
    --driver "<your headless claude_code invocation, containing {prompt}>" \
    --agent-version <version> --record --report --reporter @yourhandle \
    > stop-report.json
```

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
