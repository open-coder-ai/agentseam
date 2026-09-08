# Design

- **stdlib only.** No dependencies, ever, in the adapter path — adapters must stay
  copy-portable into other projects that vendor single files.
- **Adapters own all vendor knowledge.** Adding an agent in an existing family is a
  config entry plus a matrix row; no consumer changes.
- **Ownership-marked wiring.** Install is idempotent and uninstall is surgical: your own
  hooks in the same config are never touched.
- **The matrix carries provenance.** Every row records the version and date it was
  verified, and how.

[ARCHITECTURE.md](../ARCHITECTURE.md) explains why those choices, what they cost, and the bug
classes they exist to prevent.
