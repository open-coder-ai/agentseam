"""No local or personal data may reach a commit, a PR, or a published artifact.

This repo is developed partly by AI agents running in ephemeral containers. Those
environments carry paths, session identifiers, and account details that are of no use
to anyone reading the repo and should not be published. Reviewing for it by eye works
until the one time it does not, so it is a test.
"""

import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Each pattern is something that identifies a machine, a person, or a work session --
# never something the repository needs in order to be useful.
FORBIDDEN = {
    "absolute home path": re.compile(r"/(?:home|Users)/(?!user\b)[A-Za-z0-9._-]+/|/home/user/|C:\\\\Users\\\\"),
    "agent session id": re.compile(r"\bsession_[0-9A-Za-z]{12,}\b"),
    "assistant session link": re.compile(r"claude\.ai/code/session"),
    "container scratch path": re.compile(r"/tmp/claude-[0-9]"),
    "personal email": re.compile(
        r"\b[A-Za-z0-9._%+-]+@(?!(?:example|users\.noreply|noreply)\.)"
        r"(?:gmail|googlemail|yahoo|hotmail|outlook|proton(?:mail)?)\.[A-Za-z]{2,}\b"
    ),
}

# Documentation may legitimately name the patterns it forbids.
ALLOWED_FILES = {"tests/test_no_private_data.py"}


def _tracked_files():
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True)
    return [ROOT / line for line in out.stdout.splitlines() if line]


def test_no_private_data_in_tracked_files():
    violations = []
    for path in _tracked_files():
        rel = path.relative_to(ROOT).as_posix()
        if rel in ALLOWED_FILES or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue  # binary or unreadable: nothing textual to leak
        for label, pattern in FORBIDDEN.items():
            match = pattern.search(text)
            if match:
                # Report the KIND and the location, never the matched value itself:
                # a test that echoes the secret has published it to the CI log.
                violations.append("%s: %s at offset %d" % (rel, label, match.start()))
    assert not violations, "Private/local data in tracked files:\n" + "\n".join(violations)


def test_no_private_data_in_commit_messages():
    """Commit bodies are as public as the diff, and are far easier to leak into."""
    out = subprocess.run(
        ["git", "log", "--format=%H%x00%B%x00", "-n", "50"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    violations = []
    parts = out.stdout.split("\0")
    for i in range(0, len(parts) - 1, 2):
        sha, body = parts[i].strip(), parts[i + 1]
        if not sha:
            continue
        for label, pattern in FORBIDDEN.items():
            if pattern.search(body):
                violations.append("%s: %s" % (sha[:12], label))
    assert not violations, "Private/local data in commit messages:\n" + "\n".join(violations)
