"""PostDesignDiffCommentUseCase。architecture.md §2.1。

ComputeDesignDiffUseCaseを内部で使い、`diff.has_changes`が真の場合のみ
CommentPort.upsert()を呼ぶ(沈黙原則。§4.1をユースケースのルールとして表現し、
composition root(GitHub Actionエントリポイント)にif文を書かせない)。

沈黙原則の条件(HQ指摘、サブモジュールのimport失敗が無言でスキップされる問題への
対応): 沈黙原則は『沈黙=変更なし』が真であることに依存している。解析が部分的
(`diff.warnings`が非空)な場合、たとえ`has_changes`がfalseでも「変更なしに見える
が解析は部分的だった」という事実がレビュアーに届く必要があるため、投稿する。
沈黙するのは『変更なし かつ 警告なし』のときだけ。

画像埋め込み(HQ #36/#38の仕上げ、architecture.md §7.3): GitHub PRコメントは
生の`<svg>`タグ・data URIの`<img>`をサニタイザーで除去してしまうため、
`GitHubStyleSvgRenderer`が生成したSVGを`AssetPort`(design-diff-assets
オーファンブランチへのコミット)で永続化し、そのraw URLを`<img src="...">`
としてコメント本文に埋め込む。従来のMermaidブロックは`<details>`内の
フォールバックとして残す(画像が読み込めない環境や、テキストとしてdiffを
読みたいレビュアー向け)。
"""

from __future__ import annotations

from typing import Protocol

from design_diff.application.ports import AssetPort, CommentPort, RendererPort
from design_diff.application.use_cases.compute_design_diff import ComputeDesignDiffUseCase, DesignDiffResult


class _ComputeUseCase(Protocol):
    """ComputeDesignDiffUseCaseと同じ形を要求する(テストではフェイクを注入できるように)。"""

    def execute(
        self, base_ref: str, head_ref: str, package: str, *, include_boilerplate: bool = False
    ) -> DesignDiffResult: ...


def _render_comment_body(result: DesignDiffResult, image_url: str) -> str:
    return (
        "## design-diff\n\n"
        f'<img src="{image_url}" alt="design-diff diagram">\n\n'
        "<details>\n"
        "<summary>Mermaid (fallback)</summary>\n\n"
        f"```mermaid\n{result.mermaid}\n```\n"
        "</details>\n"
    )


class PostDesignDiffCommentUseCase:
    def __init__(
        self,
        compute_use_case: ComputeDesignDiffUseCase | _ComputeUseCase,
        comment_port: CommentPort,
        svg_renderer: RendererPort,
        asset_port: AssetPort,
    ):
        self._compute_use_case = compute_use_case
        self._comment_port = comment_port
        self._svg_renderer = svg_renderer
        self._asset_port = asset_port

    def execute(
        self, pr: int, base_ref: str, head_ref: str, package: str, *, include_boilerplate: bool = False
    ) -> DesignDiffResult:
        result = self._compute_use_case.execute(
            base_ref=base_ref, head_ref=head_ref, package=package, include_boilerplate=include_boilerplate
        )
        if result.diff.has_changes or result.diff.warnings:
            svg = self._svg_renderer.render(result.diff)
            image_url = self._asset_port.publish(
                path=f"assets/pr-{pr}.svg",
                content=svg.encode("utf-8"),
                message=f"design-diff: update diagram for PR #{pr}",
            )
            self._comment_port.upsert(pr, _render_comment_body(result, image_url))
        return result
