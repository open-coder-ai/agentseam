## What this changes

<!-- One or two sentences. What behaviour differs after this PR? -->

## Claim check

<!-- Required for anything touching adapters or the matrix. Delete if not applicable. -->

- [ ] No capability claim is widened without a mechanism behind it
- [ ] Any new/changed `MATRIX` row carries a `verified` record (version, date, method)
- [ ] Payload shapes come from a primary source (vendor doc / example repo / captured run) —
      link it here:

## Checks

- [ ] `pytest -q` passes
- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] Runtime path is still stdlib-only (no new imports outside the standard library)
- [ ] Commits are signed off (`git commit -s`)

## Notes for the reviewer

<!-- Anything you want looked at closely, or a decision you are unsure about. -->
