"""PostDesignDiffCommentUseCase のテスト。architecture.md §2.1。

ComputeDesignDiffUseCaseの結果を使って、変更があるときだけCommentPortにupsertする
(沈黙原則。HQ指示: has_changesがfalseなら投稿しない)。
"""

from __future__ import annotations

from design_diff.application.use_cases.compute_design_diff import ComputeDesignDiffUseCase, DesignDiffResult
from design_diff.application.use_cases.post_design_diff_comment import PostDesignDiffCommentUseCase
from design_diff.domain.diff import ClassDiff, RelationDiff, SnapshotDiff
from design_diff.domain.model import ClassIR


class FakeComputeUseCase:
    def __init__(self, result: DesignDiffResult):
        self._result = result
        self.calls: list[tuple] = []

    def execute(self, base_ref: str, head_ref: str, package: str, *, include_boilerplate: bool = False):
        self.calls.append((base_ref, head_ref, package, include_boilerplate))
        return self._result


class FakeCommentPort:
    def __init__(self):
        self.upserts: list[tuple[int, str]] = []

    def upsert(self, pr: int, body: str) -> None:
        self.upserts.append((pr, body))


def result_with_changes() -> DesignDiffResult:
    added = ClassIR(fqn="pkg.Battery", name="Battery")
    return DesignDiffResult(
        diff=SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff()),
        mermaid="classDiagram\n    class pkg_Battery",
        json_payload='{"has_changes": true}',
    )


def result_without_changes() -> DesignDiffResult:
    return DesignDiffResult(
        diff=SnapshotDiff(classes=ClassDiff(), relations=RelationDiff()),
        mermaid="classDiagram",
        json_payload='{"has_changes": false}',
    )


def result_without_changes_but_with_warnings() -> DesignDiffResult:
    return DesignDiffResult(
        diff=SnapshotDiff(
            classes=ClassDiff(), relations=RelationDiff(), warnings=("pkg.broken",)
        ),
        mermaid="classDiagram",
        json_payload='{"has_changes": false, "warnings": ["pkg.broken"]}',
    )


class TestPostDesignDiffCommentUseCase:
    def test_posts_a_comment_when_there_are_changes(self):
        compute_use_case = FakeComputeUseCase(result_with_changes())
        comment_port = FakeCommentPort()
        use_case = PostDesignDiffCommentUseCase(compute_use_case, comment_port)

        use_case.execute(pr=42, base_ref="main", head_ref="feature", package="pkg")

        assert len(comment_port.upserts) == 1
        pr, body = comment_port.upserts[0]
        assert pr == 42
        assert "classDiagram" in body
        assert "pkg_Battery" in body

    def test_does_not_post_when_there_are_no_changes_silence_principle(self):
        compute_use_case = FakeComputeUseCase(result_without_changes())
        comment_port = FakeCommentPort()
        use_case = PostDesignDiffCommentUseCase(compute_use_case, comment_port)

        use_case.execute(pr=42, base_ref="main", head_ref="feature", package="pkg")

        assert comment_port.upserts == []

    def test_posts_a_comment_when_there_are_no_changes_but_there_are_warnings(self):
        """沈黙原則の条件変更(HQ指摘): 『変更なし かつ 警告なし』のときだけ
        沈黙する。警告(部分解析)がある場合は、変更が無くても投稿する。
        """
        compute_use_case = FakeComputeUseCase(result_without_changes_but_with_warnings())
        comment_port = FakeCommentPort()
        use_case = PostDesignDiffCommentUseCase(compute_use_case, comment_port)

        use_case.execute(pr=42, base_ref="main", head_ref="feature", package="pkg")

        assert len(comment_port.upserts) == 1

    def test_passes_include_boilerplate_through_to_compute_use_case(self):
        compute_use_case = FakeComputeUseCase(result_without_changes())
        comment_port = FakeCommentPort()
        use_case = PostDesignDiffCommentUseCase(compute_use_case, comment_port)

        use_case.execute(pr=42, base_ref="main", head_ref="feature", package="pkg", include_boilerplate=True)

        assert compute_use_case.calls == [("main", "feature", "pkg", True)]

    def test_returns_the_computed_result_regardless_of_whether_it_posted(self):
        compute_use_case = FakeComputeUseCase(result_with_changes())
        comment_port = FakeCommentPort()
        use_case = PostDesignDiffCommentUseCase(compute_use_case, comment_port)

        result = use_case.execute(pr=42, base_ref="main", head_ref="feature", package="pkg")

        assert result.diff.has_changes is True

    def test_uses_a_real_diff_engine_end_to_end_via_real_compute_use_case(self):
        """ComputeDesignDiffUseCase(実物)と組み合わせても正しく動くことの確認。"""

        class FakeVcs:
            def checkout(self, ref: str):
                from pathlib import Path

                return Path(f"/fake/{ref}")

            def cleanup(self, path) -> None:
                pass

        class FakeExtractor:
            def extract(self, path, package: str, *, include_boilerplate: bool = False):
                if "feature" in str(path):
                    return SnapshotIRWithBattery(package)
                return SnapshotIREmpty(package)

        def SnapshotIREmpty(package):
            from design_diff.domain.model import SnapshotIR

            return SnapshotIR(package=package, classes={}, relations=frozenset())

        def SnapshotIRWithBattery(package):
            from design_diff.domain.model import SnapshotIR

            cls = ClassIR(fqn="pkg.Battery", name="Battery")
            return SnapshotIR(package=package, classes={"pkg.Battery": cls}, relations=frozenset())

        from design_diff.adapters.rendering.json_renderer import JsonRenderer
        from design_diff.adapters.rendering.mermaid_renderer import MermaidRenderer

        real_compute_use_case = ComputeDesignDiffUseCase(
            vcs=FakeVcs(),
            extractor=FakeExtractor(),
            mermaid_renderer=MermaidRenderer(),
            json_renderer=JsonRenderer(),
        )
        comment_port = FakeCommentPort()
        use_case = PostDesignDiffCommentUseCase(real_compute_use_case, comment_port)

        use_case.execute(pr=7, base_ref="main", head_ref="feature", package="pkg")

        assert len(comment_port.upserts) == 1
        assert "Battery" in comment_port.upserts[0][1]
