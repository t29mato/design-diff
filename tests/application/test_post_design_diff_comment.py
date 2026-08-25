"""PostDesignDiffCommentUseCase のテスト。architecture.md §2.1, §7.3。

ComputeDesignDiffUseCaseの結果を使って、変更(または警告)があるときだけ
SVGを生成・公開し、CommentPortにupsertする(沈黙原則。HQ指示)。
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


class FakeSvgRenderer:
    """RendererPortを構造的に満たすフェイク。渡されたdiffを記録するだけ。"""

    def __init__(self, svg_text: str = "<svg>fake</svg>"):
        self._svg_text = svg_text
        self.rendered_diffs: list = []

    def render(self, diff, *, mermaid=None, meta=None) -> str:
        self.rendered_diffs.append(diff)
        return self._svg_text


class FakeAssetPort:
    """AssetPortを構造的に満たすフェイク。publish呼び出しを記録し、固定URLを返す。"""

    def __init__(self, url: str = "https://raw.githubusercontent.com/owner/repo/abc123/assets/pr-42.svg"):
        self._url = url
        self.published: list[tuple[str, bytes, str]] = []

    def publish(self, path: str, content: bytes, message: str) -> str:
        self.published.append((path, content, message))
        return self._url


def make_use_case(
    compute_use_case, comment_port=None, svg_renderer=None, asset_port=None
) -> tuple[PostDesignDiffCommentUseCase, FakeCommentPort, FakeSvgRenderer, FakeAssetPort]:
    comment_port = comment_port or FakeCommentPort()
    svg_renderer = svg_renderer or FakeSvgRenderer()
    asset_port = asset_port or FakeAssetPort()
    use_case = PostDesignDiffCommentUseCase(compute_use_case, comment_port, svg_renderer, asset_port)
    return use_case, comment_port, svg_renderer, asset_port


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
        diff=SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(), warnings=("pkg.broken",)),
        mermaid="classDiagram",
        json_payload='{"has_changes": false, "warnings": ["pkg.broken"]}',
    )


class TestPostDesignDiffCommentUseCase:
    def test_posts_a_comment_when_there_are_changes(self):
        use_case, comment_port, _, _ = make_use_case(FakeComputeUseCase(result_with_changes()))

        use_case.execute(pr=42, base_ref="main", head_ref="feature", package="pkg")

        assert len(comment_port.upserts) == 1
        pr, body = comment_port.upserts[0]
        assert pr == 42

    def test_comment_body_embeds_the_published_image_url_and_mermaid_fallback(self):
        use_case, comment_port, _, asset_port = make_use_case(
            FakeComputeUseCase(result_with_changes()),
            asset_port=FakeAssetPort(url="https://raw.githubusercontent.com/owner/repo/deadbeef/assets/pr-42.svg"),
        )

        use_case.execute(pr=42, base_ref="main", head_ref="feature", package="pkg")

        _, body = comment_port.upserts[0]
        assert '<img src="https://raw.githubusercontent.com/owner/repo/deadbeef/assets/pr-42.svg"' in body
        assert "<details>" in body
        assert "pkg_Battery" in body  # Mermaidフォールバックの中身

    def test_svg_is_rendered_from_the_computed_diff(self):
        result = result_with_changes()
        use_case, _, svg_renderer, _ = make_use_case(FakeComputeUseCase(result))

        use_case.execute(pr=42, base_ref="main", head_ref="feature", package="pkg")

        assert svg_renderer.rendered_diffs == [result.diff]

    def test_svg_is_published_with_a_path_derived_from_the_pr_number(self):
        use_case, _, _, asset_port = make_use_case(FakeComputeUseCase(result_with_changes()))

        use_case.execute(pr=42, base_ref="main", head_ref="feature", package="pkg")

        assert len(asset_port.published) == 1
        path, content, message = asset_port.published[0]
        assert path == "assets/pr-42.svg"
        assert content == b"<svg>fake</svg>"

    def test_does_not_post_when_there_are_no_changes_silence_principle(self):
        use_case, comment_port, _, asset_port = make_use_case(FakeComputeUseCase(result_without_changes()))

        use_case.execute(pr=42, base_ref="main", head_ref="feature", package="pkg")

        assert comment_port.upserts == []
        assert asset_port.published == []  # 沈黙する場合はSVGの公開自体も行わない

    def test_posts_a_comment_when_there_are_no_changes_but_there_are_warnings(self):
        """沈黙原則の条件変更(HQ指摘): 『変更なし かつ 警告なし』のときだけ
        沈黙する。警告(部分解析)がある場合は、変更が無くても投稿する。
        """
        use_case, comment_port, _, _ = make_use_case(
            FakeComputeUseCase(result_without_changes_but_with_warnings())
        )

        use_case.execute(pr=42, base_ref="main", head_ref="feature", package="pkg")

        assert len(comment_port.upserts) == 1

    def test_passes_include_boilerplate_through_to_compute_use_case(self):
        compute_use_case = FakeComputeUseCase(result_without_changes())
        use_case, _, _, _ = make_use_case(compute_use_case)

        use_case.execute(pr=42, base_ref="main", head_ref="feature", package="pkg", include_boilerplate=True)

        assert compute_use_case.calls == [("main", "feature", "pkg", True)]

    def test_returns_the_computed_result_regardless_of_whether_it_posted(self):
        use_case, _, _, _ = make_use_case(FakeComputeUseCase(result_with_changes()))

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
        use_case, comment_port, _, _ = make_use_case(real_compute_use_case)

        use_case.execute(pr=7, base_ref="main", head_ref="feature", package="pkg")

        assert len(comment_port.upserts) == 1
        assert "Battery" in comment_port.upserts[0][1]
