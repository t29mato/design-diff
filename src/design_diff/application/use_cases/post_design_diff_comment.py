"""PostDesignDiffCommentUseCase。architecture.md §2.1。

ComputeDesignDiffUseCaseを内部で使い、`diff.has_changes`が真の場合のみ
CommentPort.upsert()を呼ぶ(沈黙原則。§4.1をユースケースのルールとして表現し、
composition root(GitHub Actionエントリポイント)にif文を書かせない)。
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
        if result.diff.has_changes:
            self._comment_port.upsert(pr, _render_comment_body(result))
        return result
