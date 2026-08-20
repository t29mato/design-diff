"""GitHubCommentPoster。CommentPortの実装。architecture.md §2.1, §8, §9。

`gh` CLIをサブプロセスとして呼ぶ(gitと同様、HTTPクライアント依存を増やさない)。
既存のdesign-diffコメントを隠しマーカーで見つけて更新する(upsert)。
同一PRで何度diffを再計算しても新規コメントが積み上がらないようにし、
通知の洪水を避ける(HQ指示)。
"""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable

_MARKER = "<!-- design-diff:auto-comment -->"


class GitHubCommentError(RuntimeError):
    """`gh` コマンドの実行に失敗した場合。"""


def _run_gh(args: list[str]):
    return subprocess.run(["gh", *args], capture_output=True, text=True)


class GitHubCommentPoster:
    """CommentPortを構造的に満たす(application.ports をimportしない。§2.2)。"""

    def __init__(self, repo: str, runner: Callable[[list[str]], object] = _run_gh):
        self._repo = repo  # "owner/repo" 形式
        self._run = runner

    def upsert(self, pr: int, body: str) -> None:
        tagged_body = f"{_MARKER}\n{body}"
        existing_id = self._find_existing_comment_id(pr)
        if existing_id is not None:
            self._patch(existing_id, tagged_body)
        else:
            self._post(pr, tagged_body)

    def _find_existing_comment_id(self, pr: int) -> int | None:
        # 手動検証で発見した実バグ: `gh api` は -f 引数があるとデフォルトでPOSTになる。
        # 一覧取得(GET)のつもりが新規コメント作成(POST)扱いになり、bodyが無いため
        # 422エラーになっていた。`-X GET` を明示して防ぐ。
        result = self._call(
            ["api", f"repos/{self._repo}/issues/{pr}/comments", "-X", "GET", "-f", "per_page=100"]
        )
        comments = json.loads(result.stdout or "[]")
        for comment in comments:
            if _MARKER in comment.get("body", ""):
                return comment["id"]
        return None

    def _post(self, pr: int, body: str) -> None:
        self._call(["api", f"repos/{self._repo}/issues/{pr}/comments", "-f", f"body={body}"])

    def _patch(self, comment_id: int, body: str) -> None:
        self._call(
            ["api", f"repos/{self._repo}/issues/comments/{comment_id}", "-X", "PATCH", "-f", f"body={body}"]
        )

    def _call(self, args: list[str]):
        result = self._run(args)
        if getattr(result, "returncode", 0) != 0:
            raise GitHubCommentError(f"gh command failed: {args}: {getattr(result, 'stderr', '')}")
        return result
