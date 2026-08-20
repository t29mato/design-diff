"""GitHub Actionエントリポイント。architecture.md §2, §2.1, §8, §9。

PRイベントでbase...headの設計diffを計算し、Mermaidブロックをコメントとして
upsertする(沈黙原則: has_changesがfalseなら投稿しない。実体は
application.use_cases.PostDesignDiffCommentUseCase)。
引数解析とアダプタの注入だけを行う薄い殻(cli/main.pyと同じ方針。HQ指摘2)。

セキュリティ(architecture.md §5.5, §9. READMEにも明記):
- 本エントリポイントを呼ぶワークフローは `pull_request_target` を使わないこと
- フォークPRからの実行にはシークレットを渡さないこと
呼び出し側のワークフローYAML側でこの制約を守る(このモジュール自体はどちらの
トリガーで呼ばれたかを判断しない。呼び出し方の安全性はワークフロー定義の責務)。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from design_diff.adapters.extraction.py2puml_extractor import Py2pumlExtractionError, Py2pumlExtractor
from design_diff.adapters.github.comment_poster import GitHubCommentPoster
from design_diff.adapters.rendering.json_renderer import JsonRenderer
from design_diff.adapters.rendering.mermaid_renderer import MermaidRenderer
from design_diff.adapters.vcs.git_worktree import GitWorktreeVcs
from design_diff.application.use_cases.compute_design_diff import ComputeDesignDiffUseCase
from design_diff.application.use_cases.post_design_diff_comment import PostDesignDiffCommentUseCase

UseCaseFactory = Callable[[Path | None, str], PostDesignDiffCommentUseCase]


@dataclass(frozen=True)
class ActionConfig:
    """コマンドライン引数を型付きの値オブジェクトにまとめたもの。

    生の`argparse.Namespace`を引き回すと属性名の綴りミスが実行時までわからない。
    値オブジェクトにすることで、main()が扱うデータの形をドメイン層のIRと同じ
    水準で明示する。
    """

    base_ref: str
    head_ref: str
    package: str
    pr: int
    repo: str
    repo_path: Path | None
    include_dunder: bool


def _default_use_case_factory(repo_path: Path | None, repo_slug: str) -> PostDesignDiffCommentUseCase:
    compute_use_case = ComputeDesignDiffUseCase(
        vcs=GitWorktreeVcs(repo_path=repo_path),
        extractor=Py2pumlExtractor(),
        mermaid_renderer=MermaidRenderer(),
        json_renderer=JsonRenderer(),
    )
    comment_port = GitHubCommentPoster(repo=repo_slug)
    return PostDesignDiffCommentUseCase(compute_use_case, comment_port)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="design-diff-action")
    parser.add_argument("base_ref", help="比較元のgit ref(通常はPRのbase SHA)")
    parser.add_argument("head_ref", help="比較先のgit ref(通常はPRのhead SHA)")
    parser.add_argument("--package", required=True, help="解析対象のPythonパッケージ名")
    parser.add_argument("--pr", type=int, required=True, help="コメント投稿先のPR番号")
    parser.add_argument("--repo", required=True, help="owner/repo 形式")
    parser.add_argument(
        "--repo-path", type=Path, default=None, help="対象gitリポジトリのパス(既定: カレントディレクトリ)"
    )
    parser.add_argument(
        "--include-dunder",
        action="store_true",
        help="ダンダーメソッド(__init__等)も含める(既定: 除外)",
    )
    return parser


def parse_config(argv: list[str] | None = None) -> ActionConfig:
    args = _build_parser().parse_args(argv)
    return ActionConfig(
        base_ref=args.base_ref,
        head_ref=args.head_ref,
        package=args.package,
        pr=args.pr,
        repo=args.repo,
        repo_path=args.repo_path,
        include_dunder=args.include_dunder,
    )


def main(argv: list[str] | None = None, use_case_factory: UseCaseFactory = _default_use_case_factory) -> int:
    config = parse_config(argv)

    use_case = use_case_factory(config.repo_path, config.repo)
    try:
        result = use_case.execute(
            pr=config.pr,
            base_ref=config.base_ref,
            head_ref=config.head_ref,
            package=config.package,
            include_dunder=config.include_dunder,
        )
    except Py2pumlExtractionError as error:
        # cli/main.pyと同じ回帰対応(実戦テストで発見)。属性の型解決は
        # typing.get_type_hints()ベースの自前実装に置き換え済みで、以前発生していた
        # 主要な失敗パターン(importのエイリアス・TYPE_CHECKING限定import等)は解消した
        # (詳細: docs/design/investigations/real-world-package-testing.md)。それでも
        # 対象コードがPython 3で実行できない場合等は失敗しうる。Actionのログに生の
        # 巨大なトレースバックではなく分かりやすい説明を残す。
        print(
            "対象コードの解析中にエラーが発生しました。design-diffは対象コードを実際に"
            "importして解析するため、対象コードがPython 3で実行できない場合(構文エラー・"
            "Python 2専用モジュールの参照等)や、対象コード側の予期しない例外により"
            "解析全体が失敗することがあります。詳細:\n" + str(error),
            file=sys.stderr,
        )
        return 1
    print(result.json_payload)  # ワークフローのログに残す(コメント投稿の有無に関わらず)
    return 0


if __name__ == "__main__":
    sys.exit(main())
