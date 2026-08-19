"""ポート定義。architecture.md §2, §2.2。

すべて `typing.Protocol`(構造的部分型)として定義する。adapters側の実装クラスは
これらを import せずに「形」を満たすだけでよい(§2.2で実測確認済み)。
application は domain にのみ依存し、adapters を import しない
(import-linterの application-purity 契約で機械的に強制)。
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from design_diff.domain.diff import SnapshotDiff
from design_diff.domain.model import SnapshotIR


class VcsPort(Protocol):
    """gitのref(ブランチ・タグ・コミット)を、解析可能なファイルツリーへ展開する。"""

    def checkout(self, ref: str) -> Path:
        """refをチェックアウトしたディレクトリへの絶対パスを返す。"""
        ...

    def cleanup(self, path: Path) -> None:
        """checkout()が作った作業ツリーを片付ける。"""
        ...


class ExtractorPort(Protocol):
    """1スナップショット分のPythonパッケージからSnapshotIRを抽出する。

    1回の呼び出しにつき1スナップショットのみを扱う(architecture.md §5.3)。
    base/headの2回呼び出しは呼び出し元(ComputeDesignDiffUseCase)が行う。
    """

    def extract(self, path: Path, package: str, *, include_dunder: bool = False) -> SnapshotIR:
        """SnapshotIRを抽出する。

        `include_dunder=False`(既定)ではダンダーメソッド(`__init__`等)を除外する
        (HQフィードバック: 表示品質。dataclass自動生成やProtocolのノイズ、
        属性差分との二重計上を防ぐ)。
        """
        ...


class RendererPort(Protocol):
    """SnapshotDiffを人間/AI可読な文字列表現へレンダリングする。"""

    def render(
        self, diff: SnapshotDiff, *, mermaid: str | None = None, meta: dict[str, str] | None = None
    ) -> str:
        """diffをレンダリングする。

        `mermaid` は、Mermaid出力を既にレンダリング済みの場合にそれを埋め込むための
        任意引数(JsonRendererがJSON中の`mermaid`フィールドを埋めるために使う。§6)。
        `meta` は `{"package":, "base_ref":, "head_ref":}` など、diffの外側にある
        付帯情報(JsonRendererが§6のトップレベルフィールドを埋めるために使う)。
        あえてカスタム型ではなく`dict`にしているのは、adaptersがapplicationの型を
        importせずに済むようにするため(§2.2と同じ理由)。
        MermaidRenderer自身はどちらの引数も無視してよい。
        """
        ...


class CommentPort(Protocol):
    """PRへのコメント投稿(作成 or 既存コメントの更新)を行う。"""

    def upsert(self, pr: int, body: str) -> None: ...
