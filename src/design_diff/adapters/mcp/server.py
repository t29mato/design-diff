"""design-diffのdiff機能をMCPツールとして公開するアダプタ。architecture.md §11。

HQ指示(2026-08-27、LLMO標準の最終ピース): design-diffのdiff機能を、公式
Model Context Protocol Python SDK(`mcp`パッケージ)経由でMCPツールとして
公開するstdioサーバーを実装する。ツール名は`analyze_design_diff`
(2つのref+package名 → 機械可読JSON diff)。

クリーンアーキテクチャ上の位置づけ: このモジュールは「ComputeDesignDiffUseCase
と同じ形のオブジェクトを返すファクトリ」を受け取ってMCPサーバーを組み立てる
だけで、具象アダプタ(Py2pumlExtractor/GitWorktreeVcs/MermaidRenderer/
JsonRenderer)はもちろん、`application`層自体もimportしない
(import-linterの`layers`契約: adaptersはapplicationより下位の層であり、
上位層に依存してはならない。他のアダプタが`application.ports`のProtocolを
importせず構造的部分型で満たしているのと同じ理由で、ここでも
`ComputeDesignDiffUseCase`を直接importせず、ローカルなProtocolで形だけを
要求する)。組み立ては composition root(design_diff.mcp.main)の責務であり、
この層(adapters)は他のアダプタパッケージとも独立でなければならない
(`adapters-independence`契約。§2.2と同じ理由でPy2pumlExtractionErrorのような
他アダプタの具象例外もimportしない。代わりに`friendly_message()`の有無を
duck typingで判定する)。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError


class _DesignDiffResult(Protocol):
    json_payload: str


class _ComputeUseCase(Protocol):
    """ComputeDesignDiffUseCaseと同じ形を要求する(このアダプタはapplication層を
    importしないため、構造的部分型でしか宣言できない。§2.2と同じ設計判断)。
    """

    def execute(
        self, *, base_ref: str, head_ref: str, package: str, include_boilerplate: bool = False
    ) -> _DesignDiffResult: ...


# repo_pathを受け取ってComputeDesignDiffUseCase相当のオブジェクトを組み立てる
# ファクトリ。MCPサーバーは1プロセス内で複数回ツール呼び出しを受けるため
# (CLI/Actionの1回きりの実行とは異なる)、呼び出しごとにrepo_pathが変わり
# うることを前提に、ツール呼び出しのたびにこのファクトリを呼んでuse caseを
# 新規に作る。
ComputeUseCaseFactory = Callable[[Path | None], _ComputeUseCase]

TOOL_NAME = "analyze_design_diff"


def create_server(use_case_factory: ComputeUseCaseFactory, *, name: str = "design-diff") -> MCPServer:
    """`analyze_design_diff`ツールを1つだけ持つMCPServerを組み立てる。"""
    server: MCPServer = MCPServer(name)

    def analyze_design_diff(
        base_ref: str,
        head_ref: str,
        package: str,
        repo_path: str | None = None,
        include_boilerplate: bool = False,
    ) -> str:
        """base_ref から head_ref への間のPythonクラス構造diffを解析し、機械可読JSONを返す。

        追加/削除/変更されたクラス、クラスごとの属性/メソッド差分、継承・
        コンポジション依存の増減、解析できなかったサブモジュールの警告を含む
        自己完結JSON(design-diffの`--format json`と同じスキーマ)を返す。

        Args:
            base_ref: 比較元のgit ref(ブランチ・タグ・コミット)
            head_ref: 比較先のgit ref
            package: 解析対象のPythonパッケージ名(importable な名前)
            repo_path: 対象gitリポジトリの絶対パス(省略時はサーバーのカレントディレクトリ)
            include_boilerplate: `__init__`等のボイラープレートメンバーも含めるか(既定: false)
        """
        use_case = use_case_factory(Path(repo_path) if repo_path else None)
        try:
            result = use_case.execute(
                base_ref=base_ref,
                head_ref=head_ref,
                package=package,
                include_boilerplate=include_boilerplate,
            )
        except Exception as error:  # noqa: BLE001 - 対象コード側のあらゆる理由での解析失敗に備える
            # Py2pumlExtractionError.friendly_message()のような、分かりやすい
            # エラー文言を持つ例外はそれを使う。具象例外クラスはimportせず、
            # 属性の有無で判定する(adapters-independence契約を守るため)。
            message = error.friendly_message() if hasattr(error, "friendly_message") else str(error)
            raise ToolError(message) from error
        return result.json_payload

    server.add_tool(analyze_design_diff, name=TOOL_NAME, structured_output=False)
    return server
