"""GitOrphanBranchAssetPublisher。AssetPortの実装。architecture.md §7.3。

HQ #36/#38の仕上げ(2026-08-25、Fable指定): design-diffがGitHub PRコメントに
埋め込むSVGを、専用のオーファンブランチ(`design-diff-assets`)へコミットし、
`raw.githubusercontent.com`のURLで参照できるようにする。生の`<svg>`タグ・
data URIの`<img>`はGitHubのコメントサニタイザーに除去されることを実機検証済み
(architecture.md §7)なので、リポジトリにコミットしてraw URL経由で参照する、
という別のアーキテクチャを取る。

**URLにコミットSHAを含める(ブランチ名ではなく)理由**: raw.githubusercontent.com
はブランチ名参照だとCDNキャッシュにより、push直後は古い内容が返り続ける可能性が
ある。コミットSHA参照は同じSHAに対する内容が不変なため、pushのたびに新しいSHA
(=新しいURL)を発行すればキャッシュ汚染の心配がない(コメント自体をupsertする
たびに、そのpush時点のSHAを含む新しいURLに差し替わる)。

**git worktreeでオーファンブランチを作る手順**(標準的なgitのレシピ):
1. `git fetch origin <branch>` が成功すれば、そのブランチは既に存在するので
   `FETCH_HEAD`からworktreeを作る
2. 失敗すれば(ブランチ未存在)、現在のHEADからworktreeを作った上で
   `git checkout --orphan <branch>` し、`git rm -rf .`で中身を空にする
   (これによりmainの履歴と一切共有しない、真に独立したオーファン履歴になる)
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path


class AssetPublishError(RuntimeError):
    """アセットの公開(コミット・push)に失敗した場合。"""


class GitOrphanBranchAssetPublisher:
    """AssetPortを構造的に満たす(application.ports をimportしない。§2.2)。"""

    def __init__(self, repo_path: Path | None, repo_slug: str, branch: str = "design-diff-assets"):
        # GitWorktreeVcsと同じ既定解決(Noneならカレントディレクトリ)。§5.2の
        # symlink罠対策として.resolve()する。
        self._repo_path = (repo_path or Path.cwd()).resolve()
        self._repo_slug = repo_slug  # "owner/repo" 形式
        self._branch = branch

    def publish(self, path: str, content: bytes, message: str) -> str:
        with tempfile.TemporaryDirectory() as tmp:
            worktree = Path(tmp) / "design-diff-assets-worktree"
            try:
                self._prepare_worktree(worktree)
                target = worktree / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(content)
                self._run(["add", "--", path], cwd=worktree)
                self._run(
                    [
                        "-c", "user.email=design-diff-bot@users.noreply.github.com",
                        "-c", "user.name=design-diff-bot",
                        "commit", "-q", "-m", message,
                    ],
                    cwd=worktree,
                )
                sha = self._run(["rev-parse", "HEAD"], cwd=worktree).stdout.strip()
                self._run(["push", "origin", f"HEAD:{self._branch}"], cwd=worktree)
            finally:
                # worktree自体はTemporaryDirectoryの削除で消えるが、.git内の登録
                # (`.git/worktrees/...`)が残ると以後の`git worktree add`で
                # 警告・衝突が起きうるため、明示的に手仕舞いする。
                subprocess.run(
                    ["git", "worktree", "remove", "--force", str(worktree)],
                    cwd=self._repo_path,
                    capture_output=True,
                    text=True,
                )

        return f"https://raw.githubusercontent.com/{self._repo_slug}/{sha}/{path}"

    def _prepare_worktree(self, worktree: Path) -> None:
        fetch = subprocess.run(
            ["git", "fetch", "origin", self._branch], cwd=self._repo_path, capture_output=True, text=True
        )
        if fetch.returncode == 0:
            self._run(["worktree", "add", "--detach", str(worktree), "FETCH_HEAD"], cwd=self._repo_path)
        else:
            # ブランチがまだ存在しない: 現在のHEADからworktreeを作り、
            # オーファンブランチとして独立させた上で中身を空にする。
            self._run(["worktree", "add", "--detach", str(worktree), "HEAD"], cwd=self._repo_path)
            self._run(["checkout", "--orphan", self._branch], cwd=worktree)
            self._run(["rm", "-rf", "."], cwd=worktree)

    def _run(self, args: list[str], cwd: Path):
        result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
        if result.returncode != 0:
            raise AssetPublishError(f"git {' '.join(args)} failed: {result.stderr.strip()}")
        return result
