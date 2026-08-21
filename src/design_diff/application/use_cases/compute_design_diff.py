"""ComputeDesignDiffUseCase。architecture.md §2.1。

VCSチェックアウト→抽出(base/head別プロセス、§5.3)→DiffEngine.diff()→レンダリング、
という一連の流れをここに閉じ込める。CLI/Actionはこれを呼ぶだけの薄い殻になる
(HQ指摘2の核心)。
"""

from __future__ import annotations

from dataclasses import dataclass

from design_diff.application.ports import ExtractorPort, RendererPort, VcsPort
from design_diff.domain.diff import DiffEngine, SnapshotDiff


@dataclass(frozen=True)
class DesignDiffResult:
    diff: SnapshotDiff
    mermaid: str
    json_payload: str


class ComputeDesignDiffUseCase:
    def __init__(
        self,
        vcs: VcsPort,
        extractor: ExtractorPort,
        mermaid_renderer: RendererPort,
        json_renderer: RendererPort,
        diff_engine: DiffEngine | None = None,
    ):
        self._vcs = vcs
        self._extractor = extractor
        self._mermaid_renderer = mermaid_renderer
        self._json_renderer = json_renderer
        self._diff_engine = diff_engine or DiffEngine()

    def execute(
        self, base_ref: str, head_ref: str, package: str, *, include_boilerplate: bool = False
    ) -> DesignDiffResult:
        base_path = self._vcs.checkout(base_ref)
        head_path = self._vcs.checkout(head_ref)
        try:
            # base/headは必ず別々の抽出呼び出しで扱う(同一プロセス内での連続inspectは
            # sys.modulesキャッシュ衝突を起こす。architecture.md §5.3)。
            # プロセス分離はExtractorPortの実装(Py2pumlExtractor)側の責務。
            base_snapshot = self._extractor.extract(
                base_path, package, include_boilerplate=include_boilerplate
            )
            head_snapshot = self._extractor.extract(
                head_path, package, include_boilerplate=include_boilerplate
            )
        finally:
            self._vcs.cleanup(base_path)
            self._vcs.cleanup(head_path)

        diff = self._diff_engine.diff(base_snapshot, head_snapshot)
        meta = {"package": package, "base_ref": base_ref, "head_ref": head_ref}
        mermaid = self._mermaid_renderer.render(diff, meta=meta)
        json_payload = self._json_renderer.render(diff, mermaid=mermaid, meta=meta)

        return DesignDiffResult(diff=diff, mermaid=mermaid, json_payload=json_payload)
