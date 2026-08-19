"""CLIエントリポイント。architecture.md §2, §8。

引数解析とアダプタの注入だけを行う薄い殻(HQ指摘2)。ロジックは持たない
(実体は application.use_cases.ComputeDesignDiffUseCase)。
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from pathlib import Path

from design_diff.adapters.extraction.py2puml_extractor import Py2pumlExtractor
from design_diff.adapters.rendering.json_renderer import JsonRenderer
from design_diff.adapters.rendering.mermaid_renderer import MermaidRenderer
from design_diff.adapters.rendering.svg_renderer import MermaidCliSvgRenderer, SvgRenderingUnavailableError
from design_diff.adapters.vcs.git_worktree import GitWorktreeVcs
from design_diff.application.use_cases.compute_design_diff import ComputeDesignDiffUseCase

UseCaseFactory = Callable[[Path | None], ComputeDesignDiffUseCase]
SvgRendererFactory = Callable[[], MermaidCliSvgRenderer]


def _default_use_case_factory(repo_path: Path | None) -> ComputeDesignDiffUseCase:
    return ComputeDesignDiffUseCase(
        vcs=GitWorktreeVcs(repo_path=repo_path),
        extractor=Py2pumlExtractor(),
        mermaid_renderer=MermaidRenderer(),
        json_renderer=JsonRenderer(),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="design-diff")
    subparsers = parser.add_subparsers(dest="command", required=True)

    diff_parser = subparsers.add_parser(
        "diff", help="base_refとhead_refの間のクラス構造diffをMermaid/JSONで出力する"
    )
    diff_parser.add_argument("base_ref", help="比較元のgit ref(ブランチ・タグ・コミット)")
    diff_parser.add_argument("head_ref", help="比較先のgit ref")
    diff_parser.add_argument("--package", required=True, help="解析対象のPythonパッケージ名")
    diff_parser.add_argument(
        "--format",
        choices=["mermaid", "json", "svg"],
        default="mermaid",
        help=(
            "出力形式(既定: mermaid)。svgはローカルプレビュー用(要mermaid-cli)。"
            "GitHub PRコメントはmermaidブロックをネイティブ描画するのでActionからはmermaid/jsonで十分"
        ),
    )
    diff_parser.add_argument(
        "--repo", type=Path, default=None, help="対象gitリポジトリのパス(既定: カレントディレクトリ)"
    )
    diff_parser.add_argument(
        "--include-dunder",
        action="store_true",
        help="ダンダーメソッド(__init__等)も含める(既定: 除外。表示ノイズ削減のため)",
    )

    return parser


def main(
    argv: list[str] | None = None,
    use_case_factory: UseCaseFactory = _default_use_case_factory,
    svg_renderer_factory: SvgRendererFactory = MermaidCliSvgRenderer,
) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "diff":
        use_case = use_case_factory(args.repo)
        result = use_case.execute(
            base_ref=args.base_ref,
            head_ref=args.head_ref,
            package=args.package,
            include_dunder=args.include_dunder,
        )

        if args.format == "json":
            print(result.json_payload)
        elif args.format == "svg":
            try:
                svg = svg_renderer_factory().render(result.mermaid)
            except SvgRenderingUnavailableError as error:
                print(str(error), file=sys.stderr)
                return 1
            print(svg)
        else:
            print(result.mermaid)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2  # pragma: no cover - argparse.error()はSystemExitを送出するため到達しない


if __name__ == "__main__":
    sys.exit(main())
