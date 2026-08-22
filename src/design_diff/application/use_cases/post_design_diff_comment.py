"""PostDesignDiffCommentUseCase。architecture.md §2.1。

ComputeDesignDiffUseCaseを内部で使い、`diff.has_changes`が真の場合のみ
CommentPort.upsert()を呼ぶ(沈黙原則。§4.1をユースケースのルールとして表現し、
composition root(GitHub Actionエントリポイント)にif文を書かせない)。

沈黙原則の条件(HQ指摘、サブモジュールのimport失敗が無言でスキップされる問題への
対応): 沈黙原則は『沈黙=変更なし』が真であることに依存している。解析が部分的
(`diff.warnings`が非空)な場合、たとえ`has_changes`がfalseでも「変更なしに見える
が解析は部分的だった」という事実がレビュアーに届く必要があるため、投稿する。
沈黙するのは『変更なし かつ 警告なし』のときだけ。
"""

from __future__ import annotations

from typing import Protocol

from design_diff.application.ports import CommentPort
from design_diff.application.use_cases.compute_design_diff import ComputeDesignDiffUseCase, DesignDiffResult


class _ComputeUseCase(Protocol):
    """ComputeDesignDiffUseCaseと同じ形を要求する(テストではフェイクを注入できるように)。"""

    def execute(
        self, base_ref: str, head_ref: str, package: str, *, include_boilerplate: bool = False
    ) -> DesignDiffResult: ...


def _render_comment_body(result: DesignDiffResult) -> str:
    return f"## design-diff\n\n```mermaid\n{result.mermaid}\n```\n"


class PostDesignDiffCommentUseCase:
    def __init__(
        self, compute_use_case: ComputeDesignDiffUseCase | _ComputeUseCase, comment_port: CommentPort
    ):
        self._compute_use_case = compute_use_case
        self._comment_port = comment_port

    def execute(
        self, pr: int, base_ref: str, head_ref: str, package: str, *, include_boilerplate: bool = False
    ) -> DesignDiffResult:
        result = self._compute_use_case.execute(
            base_ref=base_ref, head_ref=head_ref, package=package, include_boilerplate=include_boilerplate
        )
        if result.diff.has_changes or result.diff.warnings:
            self._comment_port.upsert(pr, _render_comment_body(result))
        return result
