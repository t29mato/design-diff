"""GitWorktreeVcs の統合テスト。実際のgitコマンドを使う(モックしない)。

architecture.md: base/headの2スナップショットはgit worktreeで展開して比較する。
"""

import subprocess
from pathlib import Path

import pytest

from design_diff.adapters.vcs.git_worktree import GitWorktreeError, GitWorktreeVcs


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test")

    (repo / "a.txt").write_text("v1")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "initial")
    run_git(repo, "branch", "-m", "main")

    run_git(repo, "checkout", "-q", "-b", "feature")
    (repo / "a.txt").write_text("v2")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "feature change")
    run_git(repo, "checkout", "-q", "main")

    return repo


class TestGitWorktreeVcs:
    def test_checkout_returns_a_path_with_the_ref_content(self, git_repo, tmp_path):
        vcs = GitWorktreeVcs(repo_path=git_repo, worktree_root=tmp_path / "worktrees")

        path = vcs.checkout("main")

        assert path.is_dir()
        assert (path / "a.txt").read_text() == "v1"

    def test_checkout_of_different_refs_yields_different_content(self, git_repo, tmp_path):
        vcs = GitWorktreeVcs(repo_path=git_repo, worktree_root=tmp_path / "worktrees")

        main_path = vcs.checkout("main")
        feature_path = vcs.checkout("feature")

        assert (main_path / "a.txt").read_text() == "v1"
        assert (feature_path / "a.txt").read_text() == "v2"
        assert main_path != feature_path

    def test_cleanup_removes_the_worktree_directory(self, git_repo, tmp_path):
        vcs = GitWorktreeVcs(repo_path=git_repo, worktree_root=tmp_path / "worktrees")
        path = vcs.checkout("main")

        vcs.cleanup(path)

        assert not path.exists()

    def test_cleanup_of_a_path_that_is_not_a_worktree_raises(self, git_repo, tmp_path):
        """カバレッジ補強: `git worktree remove`自体が失敗するケース
        (worktreeとして登録されていないパスを渡した場合)。
        """
        vcs = GitWorktreeVcs(repo_path=git_repo, worktree_root=tmp_path / "worktrees")
        not_a_worktree = tmp_path / "not-a-worktree"
        not_a_worktree.mkdir()

        with pytest.raises(GitWorktreeError):
            vcs.cleanup(not_a_worktree)

    def test_checkout_of_unknown_ref_raises(self, git_repo, tmp_path):
        vcs = GitWorktreeVcs(repo_path=git_repo, worktree_root=tmp_path / "worktrees")

        with pytest.raises(GitWorktreeError):
            vcs.checkout("does-not-exist")

    def test_checkout_returns_a_resolved_absolute_path(self, git_repo, tmp_path):
        """§5.2のsymlink罠と同種の問題を避けるため、常に.resolve()済みパスを返す。"""
        vcs = GitWorktreeVcs(repo_path=git_repo, worktree_root=tmp_path / "worktrees")

        path = vcs.checkout("main")

        assert path == path.resolve()
