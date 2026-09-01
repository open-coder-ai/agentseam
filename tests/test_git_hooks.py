"""The pre-commit hook must actually refresh the examples."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
HOOK = ROOT / ".githooks" / "pre-commit"

GIT = ["git", "-c", "user.name=Test", "-c", "user.email=test@example.com"]


def _run(args, cwd, **kw):
    return subprocess.run(args, cwd=str(cwd), capture_output=True, text=True, **kw)


@pytest.fixture
def clone(tmp_path):
    """A local clone with the hook enabled, so commits go through it for real."""
    if not shutil.which("git"):  # pragma: no cover - git is present everywhere we run
        pytest.skip("git unavailable")
    target = tmp_path / "clone"
    assert _run(["git", "clone", "--quiet", "--local", str(ROOT), str(target)], tmp_path).returncode == 0
    for rel in (".githooks", "examples", "src"):
        shutil.rmtree(target / rel, ignore_errors=True)
        shutil.copytree(ROOT / rel, target / rel, ignore=shutil.ignore_patterns("__pycache__"))
    assert _run(GIT + ["add", "-A"], target).returncode == 0
    if _run(["git", "status", "--porcelain"], target).stdout.strip():
        assert _run(GIT + ["commit", "-q", "-m", "sync working tree", "--no-gpg-sign"], target).returncode == 0
    assert _run(["git", "config", "core.hooksPath", ".githooks"], target).returncode == 0
    return target


def _commit(clone, message):
    return _run(GIT + ["commit", "-q", "-m", message, "--no-gpg-sign"], clone)


def test_hook_is_executable():
    """A hook without the bit set is skipped by git without a word."""
    assert HOOK.exists()
    assert HOOK.stat().st_mode & 0o111, "pre-commit hook is not executable"


def test_changing_an_adapter_refreshes_the_pages_in_the_same_commit(clone):
    """The point of the hook: the fix and its regenerated output land together."""
    adapter = clone / "src" / "agentseam" / "adapters" / "windsurf.py"
    adapter.write_text(adapter.read_text().replace("cannot prompt for confirmation", "has no confirmation prompt"))
    assert _run(GIT + ["add", "src/agentseam/adapters/windsurf.py"], clone).returncode == 0

    result = _commit(clone, "change windsurf wording")
    assert result.returncode == 0, result.stderr

    committed = _run(["git", "show", "--name-only", "--format=", "HEAD"], clone).stdout.split()
    assert "examples/generated/windsurf.md" in committed
    assert "has no confirmation prompt" in (clone / "examples" / "generated" / "windsurf.md").read_text()

    check = _run(["python3", "examples/generate.py", "--check"], clone)
    assert check.returncode == 0, check.stderr


def test_a_commit_that_touches_nothing_generated_from_is_left_alone(clone):
    """Regenerating on every commit would be noise, and noise gets hooks uninstalled."""
    readme = clone / "README.md"
    readme.write_text(readme.read_text() + "\n<!-- unrelated edit -->\n")
    assert _run(GIT + ["add", "README.md"], clone).returncode == 0

    result = _commit(clone, "docs tweak")
    assert result.returncode == 0, result.stderr
    committed = _run(["git", "show", "--name-only", "--format=", "HEAD"], clone).stdout.split()
    assert committed == ["README.md"]
    assert "refreshed" not in result.stdout + result.stderr


@pytest.mark.parametrize("source", ["examples/scenarios.py", "examples/vendor_payloads.py"])
def test_editing_any_generator_input_refreshes(clone, source):
    """The pages are generated from more than src/, and the hook has to know all of it."""
    target = clone / source
    target.write_text(target.read_text().replace("EXAMPLE-PLACEHOLDER-NOT-A-KEY", "EXAMPLE-PLACEHOLDER-XYZ"))
    if target.read_text() == (ROOT / source).read_text():
        pytest.skip("%s does not carry the placeholder" % source)
    assert _run(GIT + ["add", source], clone).returncode == 0

    assert _commit(clone, "change the placeholder").returncode == 0
    committed = _run(["git", "show", "--name-only", "--format=", "HEAD"], clone).stdout.split()
    assert any(f.startswith("examples/generated/") for f in committed)


def test_the_hook_does_not_block_a_commit_when_it_cannot_run(clone):
    """A developer without python3 gets a warning, not a repository they cannot commit to."""
    assert "skipping example refresh" in HOOK.read_text()
    assert "exit 0" in HOOK.read_text()
