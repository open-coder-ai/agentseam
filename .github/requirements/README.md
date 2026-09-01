# Pinned CI tooling

Every `pip install` in a workflow reads one of these lockfiles with
`--require-hashes`, so a CI job installs the exact artifacts recorded here or
fails. The `.in` file is the input; the `.txt` beside it is generated, and its
header carries the command that produced it.

| Lockfile | Used by | Resolved for |
|---|---|---|
| `dev.txt` | `ci.yml` test, `release.yml` build | universal — Python 3.9-3.13, Linux/macOS/Windows |
| `lint.txt` | `ci.yml` lint | Python 3.11 |
| `assets.txt` | `ci.yml` brand-assets | Python 3.12 |
| `build.txt` | `release.yml` build | Python 3.11 |
| `zizmor.txt` | `security.yml` zizmor | Python 3.11 |
| `semgrep.txt` | `security.yml` semgrep | Python 3.11 |

`dev.txt` is the only universal one because it is the only lockfile a job
installs on more than one Python version or operating system; the rest each
serve a single `ubuntu-latest` job whose Python version is fixed in the
workflow. Re-resolve after editing an `.in`, or to refresh a pin dependabot
has not:

```
uv pip compile --universal --generate-hashes --python-version 3.9 -o dev.txt dev.in
```

Substitute the header's own command for the other five.
