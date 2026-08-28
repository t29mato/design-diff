"""GitHub Actionエントリポイント。architecture.md §2, §2.1, §7.3, §8, §9。

PRイベントでbase...headの設計diffを計算し、GitHub diff風のネイティブSVG
(`GitHubStyleSvgRenderer`)をdesign-diff-assetsオーファンブランチへコミット
(`GitOrphanBranchAssetPublisher`)して、そのraw URLを`<img>`としてコメントに
埋め込む。従来のMermaidブロックは`<details>`内のフォールバックとして残す
(沈黙原則: has_changesがfalseかつwarningsが空なら投稿しない。実体は
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
from design_diff.adapters.github.asset_publisher import GitOrphanBranchAssetPublisher
from design_diff.adapters.github.comment_poster import GitHubCommentPoster
from design_diff.adapters.rendering.github_style_svg_renderer import GitHubStyleSvgRenderer
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
    svg_renderer = GitHubStyleSvgRenderer()
    asset_port = GitOrphanBranchAssetPublisher(repo_path=repo_path, repo_slug=repo_slug)
    return PostDesignDiffCommentUseCase(compute_use_case, comment_port, svg_renderer, asset_port)


def _build_parser() -> argparse.ArgumentParser:
    # cli/main.pyと同じ理由(2026-08-29の点検)でhelp文言は英語にしている。
    # design-diff-actionの--helpを直接見るのはワークフローYAMLを手で調整する
    # 人がほとんどだが、公開インターフェースとしての一貫性を優先した。
    parser = argparse.ArgumentParser(prog="design-diff-action")
    parser.add_argument("base_ref", help="The ref to compare from (usually the PR's base SHA)")
    parser.add_argument("head_ref", help="The ref to compare to (usually the PR's head SHA)")
    parser.add_argument("--package", required=True, help="The importable Python package name to analyze")
    parser.add_argument("--pr", type=int, required=True, help="The PR number to post the comment to")
    parser.add_argument("--repo", required=True, help="\"owner/repo\" format")
    parser.add_argument(
        "--repo-path", type=Path, default=None, help="Path to the git repository to analyze (default: cwd)"
    )
    parser.add_argument(
        "--include-dunder",
        action="store_true",
        help="Also include dunder methods such as __init__ (default: excluded)",
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
            # ActionConfig.include_dunderはPython向けの利用者向け語彙のまま(意図的)。
            # application層のexecute()へは言語非依存な語彙で渡す
            # (多言語拡張性の評価。docs/design/multi-language-extensibility-assessment.md)。
            include_boilerplate=config.include_dunder,
        )
    except Py2pumlExtractionError as error:
        # cli/main.pyと同じ回帰対応(実戦テストで発見)。以前はActionのログに生の
        # 巨大なトレースバックがそのまま出ていた。friendly_message()が分かりやすい
        # 説明を組み立てる(詳細: docs/design/investigations/real-world-package-testing.md)。
        print(error.friendly_message(), file=sys.stderr)
        return 1
    print(result.json_payload)  # ワークフローのログに残す(コメント投稿の有無に関わらず)
    return 0


if __name__ == "__main__":
    sys.exit(main())
