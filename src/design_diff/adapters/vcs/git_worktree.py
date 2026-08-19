"""GitWorktreeVcs。VcsPortの実装。

gitのref(ブランチ・タグ・コミット)を `git worktree add` でファイルツリーに展開する。
application.ports.VcsPort を import しない(構造的部分型で満たす。architecture.md §2.2)。
"""

from __future__ import annotations

import re
import subprocess
import uuid
from pathlib import Path


class GitWorktreeError(RuntimeError):
    """git worktree の作成・削除に失敗した場合。"""


_UNSAFE_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def _sanitize_ref_for_dirname(ref: str) -> str:
    return _UNSAFE_CHARS.sub("-", ref).strip("-") or "ref"


class GitWorktreeVcs:
    def __init__(self, repo_path: Path | None = None, worktree_root: Path | None = None):
        self._repo_path = (repo_path or Path.cwd()).resolve()
        self._worktree_root = (worktree_root or (self._repo_path / ".design-diff-worktrees")).resolve()

    def checkout(self, ref: str) -> Path:
        self._worktree_root.mkdir(parents=True, exist_ok=True)
        target = self._worktree_root / f"{_sanitize_ref_for_dirname(ref)}-{uuid.uuid4().hex[:8]}"

        result = subprocess.run(
            ["git", "worktree", "add", "--detach", str(target), ref],
            cwd=self._repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise GitWorktreeError(f"git worktree add failed for ref={ref!r}: {result.stderr.strip()}")

        return target.resolve()

    def cleanup(self, path: Path) -> None:
        result = subprocess.run(
            ["git", "worktree", "remove", "--force", str(path)],
            cwd=self._repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise GitWorktreeError(f"git worktree remove failed for path={path}: {result.stderr.strip()}")
