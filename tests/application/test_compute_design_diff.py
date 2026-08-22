"""ComputeDesignDiffUseCase のテスト。architecture.md §2.1。

フェイクのVcsPort/ExtractorPort/RendererPortを注入し、E2E(実際のgit worktree・
実際のpy2puml実行)を待たずにユースケースの振る舞いを検証する(HQ指摘2の狙い)。
フェイクはPortをimportして継承せず、構造的部分型として振る舞う(§2.2の設計に合わせる)。
"""

from __future__ import annotations

from pathlib import Path

from design_diff.application.use_cases.compute_design_diff import ComputeDesignDiffUseCase
from design_diff.domain.diff import DiffEngine
from design_diff.domain.model import ClassIR, SnapshotIR


class FakeVcs:
    """VcsPortを構造的に満たすフェイク。checkoutされたrefを記録する。"""

    def __init__(self):
        self.checked_out_refs: list[str] = []
        self.cleaned_up_paths: list[Path] = []

    def checkout(self, ref: str) -> Path:
        self.checked_out_refs.append(ref)
        return Path(f"/fake/worktree/{ref}")

    def cleanup(self, path: Path) -> None:
        self.cleaned_up_paths.append(path)


class FakeExtractor:
    """VcsPortが返したpathごとに事前に用意したSnapshotIRを返すフェイク。"""

    def __init__(self, snapshots_by_path: dict[str, SnapshotIR]):
        self._snapshots_by_path = snapshots_by_path
        self.extracted_paths: list[Path] = []
        self.include_boilerplate_calls: list[bool] = []

    def extract(self, path: Path, package: str, *, include_boilerplate: bool = False) -> SnapshotIR:
        self.extracted_paths.append(path)
        self.include_boilerplate_calls.append(include_boilerplate)
        return self._snapshots_by_path[str(path)]


class FakeRenderer:
    """RendererPortを満たすフェイク。呼ばれたことと引数を記録するだけ。"""

    def __init__(self, name: str):
        self.name = name
        self.calls: list[tuple] = []

    def render(self, diff, *, mermaid: str | None = None, meta: dict | None = None) -> str:
        self.calls.append((diff, mermaid, meta))
        return f"<{self.name} output>"


def empty_snapshot(package: str) -> SnapshotIR:
    return SnapshotIR(package=package, classes={}, relations=frozenset())


def snapshot_with_class(package: str, fqn: str) -> SnapshotIR:
    cls = ClassIR(fqn=fqn, name=fqn.rsplit(".", 1)[-1])
    return SnapshotIR(package=package, classes={fqn: cls}, relations=frozenset())


class TestComputeDesignDiffUseCase:
    def test_checks_out_both_refs_and_extracts_both_snapshots(self):
        vcs = FakeVcs()
        extractor = FakeExtractor(
            {
                "/fake/worktree/main": empty_snapshot("pkg"),
                "/fake/worktree/feature": empty_snapshot("pkg"),
            }
        )
        use_case = ComputeDesignDiffUseCase(
            vcs=vcs,
            extractor=extractor,
            mermaid_renderer=FakeRenderer("mermaid"),
            json_renderer=FakeRenderer("json"),
        )

        use_case.execute(base_ref="main", head_ref="feature", package="pkg")

        assert vcs.checked_out_refs == ["main", "feature"]
        assert extractor.extracted_paths == [Path("/fake/worktree/main"), Path("/fake/worktree/feature")]

    def test_cleans_up_both_worktrees_even_when_result_has_no_changes(self):
        vcs = FakeVcs()
        extractor = FakeExtractor(
            {
                "/fake/worktree/main": empty_snapshot("pkg"),
                "/fake/worktree/feature": empty_snapshot("pkg"),
            }
        )
        use_case = ComputeDesignDiffUseCase(
            vcs=vcs,
            extractor=extractor,
            mermaid_renderer=FakeRenderer("mermaid"),
            json_renderer=FakeRenderer("json"),
        )

        use_case.execute(base_ref="main", head_ref="feature", package="pkg")

        assert set(vcs.cleaned_up_paths) == {Path("/fake/worktree/main"), Path("/fake/worktree/feature")}

    def test_cleans_up_worktrees_even_when_extraction_raises(self):
        vcs = FakeVcs()

        class FailingExtractor:
            def extract(self, path: Path, package: str, *, include_boilerplate: bool = False) -> SnapshotIR:
                raise RuntimeError("boom")

        use_case = ComputeDesignDiffUseCase(
            vcs=vcs,
            extractor=FailingExtractor(),
            mermaid_renderer=FakeRenderer("mermaid"),
            json_renderer=FakeRenderer("json"),
        )

        try:
            use_case.execute(base_ref="main", head_ref="feature", package="pkg")
        except RuntimeError:
            pass

        assert Path("/fake/worktree/main") in vcs.cleaned_up_paths

    def test_diffs_the_two_extracted_snapshots_via_diff_engine(self):
        vcs = FakeVcs()
        extractor = FakeExtractor(
            {
                "/fake/worktree/main": empty_snapshot("pkg"),
                "/fake/worktree/feature": snapshot_with_class("pkg", "pkg.Battery"),
            }
        )
        use_case = ComputeDesignDiffUseCase(
            vcs=vcs,
            extractor=extractor,
            mermaid_renderer=FakeRenderer("mermaid"),
            json_renderer=FakeRenderer("json"),
        )

        result = use_case.execute(base_ref="main", head_ref="feature", package="pkg")

        assert [c.fqn for c in result.diff.classes.added] == ["pkg.Battery"]
        assert result.diff.has_changes is True

    def test_propagates_skipped_modules_from_extractor_into_diff_warnings(self):
        """発見した問題(サブモジュールのimport失敗が無言でスキップされる)への対応。
        extractorがSnapshotIR.skipped_modulesに記録した内容が、実際のDiffEngineを
        通ってresult.diff.warningsまで届くこと。
        """
        vcs = FakeVcs()
        head_snapshot = SnapshotIR(
            package="pkg", classes={}, relations=frozenset(), skipped_modules=("pkg.broken",)
        )
        extractor = FakeExtractor(
            {
                "/fake/worktree/main": empty_snapshot("pkg"),
                "/fake/worktree/feature": head_snapshot,
            }
        )
        use_case = ComputeDesignDiffUseCase(
            vcs=vcs,
            extractor=extractor,
            mermaid_renderer=FakeRenderer("mermaid"),
            json_renderer=FakeRenderer("json"),
        )

        result = use_case.execute(base_ref="main", head_ref="feature", package="pkg")

        assert result.diff.warnings == ("pkg.broken",)
        assert result.diff.has_changes is False

    def test_renders_mermaid_and_json_from_the_computed_diff(self):
        vcs = FakeVcs()
        extractor = FakeExtractor(
            {
                "/fake/worktree/main": empty_snapshot("pkg"),
                "/fake/worktree/feature": empty_snapshot("pkg"),
            }
        )
        mermaid_renderer = FakeRenderer("mermaid")
        json_renderer = FakeRenderer("json")
        use_case = ComputeDesignDiffUseCase(
            vcs=vcs, extractor=extractor, mermaid_renderer=mermaid_renderer, json_renderer=json_renderer
        )

        result = use_case.execute(base_ref="main", head_ref="feature", package="pkg")

        assert result.mermaid == "<mermaid output>"
        assert result.json_payload == "<json output>"
        # JsonRendererにはMermaidの結果が渡され、JSON側にmermaidを埋め込める(§6)
        assert json_renderer.calls[0][1] == "<mermaid output>"

    def test_passes_package_and_refs_as_meta_to_both_renderers(self):
        vcs = FakeVcs()
        extractor = FakeExtractor(
            {
                "/fake/worktree/main": empty_snapshot("pkg"),
                "/fake/worktree/feature": empty_snapshot("pkg"),
            }
        )
        mermaid_renderer = FakeRenderer("mermaid")
        json_renderer = FakeRenderer("json")
        use_case = ComputeDesignDiffUseCase(
            vcs=vcs, extractor=extractor, mermaid_renderer=mermaid_renderer, json_renderer=json_renderer
        )

        use_case.execute(base_ref="main", head_ref="feature", package="pkg")

        expected_meta = {"package": "pkg", "base_ref": "main", "head_ref": "feature"}
        assert mermaid_renderer.calls[0][2] == expected_meta
        assert json_renderer.calls[0][2] == expected_meta

    def test_include_boilerplate_defaults_to_false_and_is_passed_to_extractor(self):
        vcs = FakeVcs()
        extractor = FakeExtractor(
            {
                "/fake/worktree/main": empty_snapshot("pkg"),
                "/fake/worktree/feature": empty_snapshot("pkg"),
            }
        )
        use_case = ComputeDesignDiffUseCase(
            vcs=vcs,
            extractor=extractor,
            mermaid_renderer=FakeRenderer("mermaid"),
            json_renderer=FakeRenderer("json"),
        )

        use_case.execute(base_ref="main", head_ref="feature", package="pkg")

        assert extractor.include_boilerplate_calls == [False, False]

    def test_include_boilerplate_true_is_passed_through_to_both_extract_calls(self):
        vcs = FakeVcs()
        extractor = FakeExtractor(
            {
                "/fake/worktree/main": empty_snapshot("pkg"),
                "/fake/worktree/feature": empty_snapshot("pkg"),
            }
        )
        use_case = ComputeDesignDiffUseCase(
            vcs=vcs,
            extractor=extractor,
            mermaid_renderer=FakeRenderer("mermaid"),
            json_renderer=FakeRenderer("json"),
        )

        use_case.execute(base_ref="main", head_ref="feature", package="pkg", include_boilerplate=True)

        assert extractor.include_boilerplate_calls == [True, True]

    def test_uses_injected_diff_engine_when_provided(self):
        vcs = FakeVcs()
        extractor = FakeExtractor(
            {
                "/fake/worktree/main": empty_snapshot("pkg"),
                "/fake/worktree/feature": empty_snapshot("pkg"),
            }
        )

        class RecordingDiffEngine(DiffEngine):
            def __init__(self):
                self.called = False

            def diff(self, base, head):
                self.called = True
                return super().diff(base, head)

        diff_engine = RecordingDiffEngine()
        use_case = ComputeDesignDiffUseCase(
            vcs=vcs,
            extractor=extractor,
            mermaid_renderer=FakeRenderer("mermaid"),
            json_renderer=FakeRenderer("json"),
            diff_engine=diff_engine,
        )

        use_case.execute(base_ref="main", head_ref="feature", package="pkg")

        assert diff_engine.called is True
