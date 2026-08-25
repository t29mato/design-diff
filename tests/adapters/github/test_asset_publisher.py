"""GitOrphanBranchAssetPublisher の統合テスト。実際のgitコマンドを使う(モックしない)。

architecture.md §7.3: PRコメントに埋め込むSVGを専用のオーファンブランチへ
コミットし、raw.githubusercontent.comのURL(コミットSHA固定)で参照できるように
する。git_worktree.pyのテストと同じ流儀(実ローカルリポジトリ+実git操作)で検証する。
"""

import subprocess
from pathlib import Path

import pytest

from design_diff.adapters.github.asset_publisher import AssetPublishError, GitOrphanBranchAssetPublisher


def run_git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def repo_with_remote(tmp_path) -> Path:
    """originを持つ実リポジトリ(ローカルのbareリポジトリを模擬リモートとして使う)。"""
    remote = tmp_path / "remote.git"
    remote.mkdir()
    run_git(remote, "init", "-q", "--bare")

    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test")
    (repo / "README.md").write_text("hello")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "initial")
    run_git(repo, "branch", "-m", "main")
    run_git(repo, "remote", "add", "origin", str(remote))
    run_git(repo, "push", "-q", "origin", "main")

    return repo


class TestGitOrphanBranchAssetPublisherCreatesBranch:
    def test_creates_the_orphan_branch_when_it_does_not_exist_yet(self, repo_with_remote):
        publisher = GitOrphanBranchAssetPublisher(repo_path=repo_with_remote, repo_slug="owner/repo")

        url = publisher.publish(path="assets/pr-1.svg", content=b"<svg>v1</svg>", message="update pr 1")

        assert url.startswith("https://raw.githubusercontent.com/owner/repo/")
        assert url.endswith("/assets/pr-1.svg")

    def test_published_content_is_actually_on_the_remote_branch(self, repo_with_remote, tmp_path):
        publisher = GitOrphanBranchAssetPublisher(repo_path=repo_with_remote, repo_slug="owner/repo")
        publisher.publish(path="assets/pr-1.svg", content=b"<svg>hello</svg>", message="update pr 1")

        remote = repo_with_remote.parent / "remote.git"
        clone = tmp_path / "clone"
        run_git(tmp_path, "clone", "-q", "-b", "design-diff-assets", str(remote), str(clone))

        assert (clone / "assets" / "pr-1.svg").read_bytes() == b"<svg>hello</svg>"

    def test_orphan_branch_shares_no_history_with_main(self, repo_with_remote, tmp_path):
        publisher = GitOrphanBranchAssetPublisher(repo_path=repo_with_remote, repo_slug="owner/repo")
        publisher.publish(path="assets/pr-1.svg", content=b"<svg/>", message="update pr 1")

        result = subprocess.run(
            ["git", "merge-base", "main", "design-diff-assets"],
            cwd=repo_with_remote,
            capture_output=True,
            text=True,
        )
        assert result.returncode != 0  # 共通の祖先が無い(真にオーファン)

    def test_main_worktree_is_left_untouched(self, repo_with_remote):
        """アセット公開処理が、呼び出し元のメインチェックアウトの状態を汚さないこと。"""
        publisher = GitOrphanBranchAssetPublisher(repo_path=repo_with_remote, repo_slug="owner/repo")
        publisher.publish(path="assets/pr-1.svg", content=b"<svg/>", message="update pr 1")

        status = run_git(repo_with_remote, "status", "--porcelain")
        assert status.stdout.strip() == ""
        assert not (repo_with_remote / "assets").exists()


class TestGitOrphanBranchAssetPublisherUpdatesBranch:
    def test_second_publish_updates_the_file_and_adds_a_new_commit(self, repo_with_remote, tmp_path):
        publisher = GitOrphanBranchAssetPublisher(repo_path=repo_with_remote, repo_slug="owner/repo")
        url1 = publisher.publish(path="assets/pr-1.svg", content=b"<svg>v1</svg>", message="update pr 1 (1)")
        url2 = publisher.publish(path="assets/pr-1.svg", content=b"<svg>v2</svg>", message="update pr 1 (2)")

        assert url1 != url2  # コミットSHAが変わるため、URLも変わる(キャッシュ汚染対策)

        remote = repo_with_remote.parent / "remote.git"
        clone = tmp_path / "clone"
        run_git(tmp_path, "clone", "-q", "-b", "design-diff-assets", str(remote), str(clone))
        assert (clone / "assets" / "pr-1.svg").read_bytes() == b"<svg>v2</svg>"

        log = run_git(clone, "log", "--oneline", "design-diff-assets")
        assert len(log.stdout.strip().splitlines()) == 2

    def test_publishing_a_different_pr_path_does_not_remove_other_prs_assets(
        self, repo_with_remote, tmp_path
    ):
        """同じオーファンブランチ上で複数PR分のアセットが共存できること。"""
        publisher = GitOrphanBranchAssetPublisher(repo_path=repo_with_remote, repo_slug="owner/repo")
        publisher.publish(path="assets/pr-1.svg", content=b"<svg>pr1</svg>", message="update pr 1")
        publisher.publish(path="assets/pr-2.svg", content=b"<svg>pr2</svg>", message="update pr 2")

        remote = repo_with_remote.parent / "remote.git"
        clone = tmp_path / "clone"
        run_git(tmp_path, "clone", "-q", "-b", "design-diff-assets", str(remote), str(clone))
        assert (clone / "assets" / "pr-1.svg").read_bytes() == b"<svg>pr1</svg>"
        assert (clone / "assets" / "pr-2.svg").read_bytes() == b"<svg>pr2</svg>"


class TestGitOrphanBranchAssetPublisherErrors:
    def test_raises_asset_publish_error_when_remote_is_unreachable(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        run_git(repo, "init", "-q")
        run_git(repo, "config", "user.email", "test@example.com")
        run_git(repo, "config", "user.name", "Test")
        (repo / "a.txt").write_text("v1")
        run_git(repo, "add", ".")
        run_git(repo, "commit", "-q", "-m", "initial")
        run_git(repo, "remote", "add", "origin", str(tmp_path / "does-not-exist"))

        publisher = GitOrphanBranchAssetPublisher(repo_path=repo, repo_slug="owner/repo")

        with pytest.raises(AssetPublishError):
            publisher.publish(path="assets/pr-1.svg", content=b"<svg/>", message="update pr 1")
