"""Files the repo's own contents point elsewhere are never written: install and instructions stay inside it."""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agentseam import install, instructions  # noqa: E402
from agentseam.install_atomic import PathEscapesRepoError  # noqa: E402

pytestmark = pytest.mark.skipif(not hasattr(os, "symlink") or sys.platform == "win32", reason="needs POSIX symlinks")


@pytest.fixture
def sandbox(tmp_path):
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    repo.mkdir()
    outside.mkdir()
    return repo, outside


def test_instructions_refuse_a_file_linked_outside_the_repo(sandbox):
    repo, outside = sandbox
    target = outside / "gitconfig"
    target.write_text("[user]\n", encoding="utf-8")
    (repo / "AGENTS.md").symlink_to(target)
    with pytest.raises(PathEscapesRepoError):
        instructions.write("rule", repo_root=str(repo))
    assert target.read_text(encoding="utf-8") == "[user]\n"


def test_instructions_refuse_a_dangling_link(sandbox):
    repo, outside = sandbox
    (repo / "AGENTS.md").symlink_to(outside / "new-file")
    with pytest.raises(PathEscapesRepoError):
        instructions.write("rule", repo_root=str(repo))
    assert not (outside / "new-file").exists()


def test_instructions_refuse_a_directory_linked_outside_the_repo(sandbox):
    repo, outside = sandbox
    (repo / ".junie").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathEscapesRepoError):
        instructions.write("rule", targets=["junie"], repo_root=str(repo))
    assert os.listdir(outside) == []


def test_instructions_still_write_through_a_link_that_stays_inside(sandbox):
    repo, _outside = sandbox
    (repo / "AGENTS.md").write_text("# mine\n", encoding="utf-8")
    (repo / "CLAUDE.md").symlink_to("AGENTS.md")
    instructions.write("rule", targets=["claude_code"], repo_root=str(repo))
    assert "rule" in (repo / "AGENTS.md").read_text(encoding="utf-8")


def test_remove_refuses_a_file_linked_outside_the_repo(sandbox):
    repo, outside = sandbox
    target = outside / "f.md"
    target.write_text("<!-- agentseam:begin -->\nx\n<!-- agentseam:end -->\n", encoding="utf-8")
    (repo / "AGENTS.md").symlink_to(target)
    with pytest.raises(PathEscapesRepoError):
        instructions.remove(repo_root=str(repo))
    assert "agentseam:begin" in target.read_text(encoding="utf-8")


@pytest.mark.parametrize("agent", ["claude_code", "mistral_vibe"])
def test_install_refuses_a_config_linked_outside_the_repo(sandbox, agent):
    repo, outside = sandbox
    rel = install.config_path(agent, str(repo))
    os.makedirs(os.path.dirname(rel), exist_ok=True)
    target = outside / "victim"
    target.write_text("{}" if agent == "claude_code" else "", encoding="utf-8")
    os.symlink(target, rel)
    before = target.read_text(encoding="utf-8")
    with pytest.raises(PathEscapesRepoError):
        install.install(agent, ["pre_tool"], "python3 hook.py", str(repo))
    with pytest.raises(PathEscapesRepoError):
        install.uninstall(agent, str(repo))
    assert target.read_text(encoding="utf-8") == before


def test_install_refuses_a_config_directory_linked_outside_the_repo(sandbox):
    repo, outside = sandbox
    (repo / ".claude").symlink_to(outside, target_is_directory=True)
    with pytest.raises(PathEscapesRepoError):
        install.install("claude_code", ["pre_tool"], "python3 hook.py", str(repo))
    assert os.listdir(outside) == []


def test_install_refuses_a_hooks_directory_linked_outside_the_repo(sandbox):
    repo, outside = sandbox
    rel = install.config_path("cline", str(repo))
    os.makedirs(os.path.dirname(rel), exist_ok=True)
    os.symlink(outside, rel, target_is_directory=True)
    with pytest.raises(PathEscapesRepoError):
        install.install("cline", ["pre_tool"], "python3 hook.py", str(repo))
    assert os.listdir(outside) == []


def test_install_still_works_through_a_link_that_stays_inside(sandbox):
    repo, _outside = sandbox
    (repo / "real").mkdir()
    (repo / ".claude").symlink_to("real", target_is_directory=True)
    path = install.install("claude_code", ["pre_tool"], "python3 hook.py", str(repo))
    assert os.path.isfile(path)
    assert (repo / "real" / "settings.json").is_file()
