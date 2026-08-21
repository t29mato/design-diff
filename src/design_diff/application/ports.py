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
    """1スナップショット分の対象コードからSnapshotIRを抽出する。

    1回の呼び出しにつき1スナップショットのみを扱う(architecture.md §5.3)。
    base/headの2回呼び出しは呼び出し元(ComputeDesignDiffUseCase)が行う。

    多言語拡張性の評価(docs/design/multi-language-extensibility-assessment.md)
    で判明した規約: 実装が返す`SnapshotIR`内の`ClassIR.fqn`は、対象言語の実際の
    パス区切り文字が何であれ**ドット区切りに正規化して返すこと**
    (`adapters/rendering/mermaid_renderer.py`のnamespaceグループ化・短縮ラベル
    生成がドット区切りを前提にしているため)。
    """

    def extract(self, path: Path, package: str, *, include_boilerplate: bool = False) -> SnapshotIR:
        """SnapshotIRを抽出する。

        `include_boilerplate=False`(既定)では、対象言語のエコシステムにおける
        自動生成・定型的なボイラープレートメンバー(Pythonなら`__init__`等の
        ダンダーメソッド)を除外する(HQフィードバック: 表示品質。dataclass
        自動生成やProtocolのノイズ、属性差分との二重計上を防ぐ)。何をボイラー
        プレートと見なすかは対象言語ごとに異なるため、その判定はこのPortの
        実装(アダプタ)側の責務とする。
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
