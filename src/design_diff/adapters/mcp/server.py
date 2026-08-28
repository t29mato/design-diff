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
他アダプタの具象例外もimportしない。エラー時は`str(error)`のテキストパターン
だけを見て英語のガイダンスを組み立てる。§14.6参照)。

**言語方針(2026-08-29の点検で追記)**: このモジュールが組み立てる、MCP
クライアントに直接見える文言(ツールのdocstring・エラーメッセージ)は英語で
書く。design-diffの内部コメント・CLI/Actionのエラーメッセージは引き続き
日本語だが、MCPツールはプロトコル経由で任意のクライアントに公開される
「公開API」であり、READMEと同じ扱い(英語)にすべきという判断による。
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


def _build_error_message(error_text: str) -> str:
    """解析失敗時のToolErrorメッセージを英語で組み立てる(このツール自体の
    説明文が英語であるため)。CLI/Actionの`friendly_message()`と内容は似るが、
    具象例外クラスをimportできない制約の下で書く必要がある(モジュール
    docstring参照)ため、`str(error)`のテキストにModuleNotFoundError/
    ImportErrorという単語が含まれるかどうかだけで判定する。
    """
    message = (
        "Analysis failed. design-diff imports the analyzed code to extract its "
        "class structure, so a syntax error, Python-2-only code, or an "
        "unexpected exception in the target code can make the whole analysis "
        "fail."
    )
    if "ModuleNotFoundError" in error_text or "ImportError" in error_text:
        message += (
            " This looks like a missing dependency: design-diff imports the "
            "analyzed package's own code, so that package's runtime "
            "dependencies must also be installed in this environment (this is "
            "not a bug in design-diff itself). Install the analyzed package's "
            "dependencies and try again."
        )
    return f"{message}\n\nDetails:\n{error_text}"


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
        """Analyze the class-level structure diff between two git refs of a Python package.

        Returns a self-contained JSON document (the same schema as
        `design-diff diff ... --format json`): added/removed/modified
        classes, per-class attribute/method diffs, inheritance/composition
        edges gained or lost, and a `warnings` array listing any submodule
        that failed to import (empty means the analysis covered the whole
        package). `has_changes: false` together with `warnings: []` means no
        structural change was detected and the analysis was complete.

        Executes the analyzed code via import (in an isolated subprocess) —
        only call this against trusted, same-repo code.

        Args:
            base_ref: The ref to compare from (branch, tag, or commit).
            head_ref: The ref to compare to.
            package: The importable top-level package name to analyze (not
                the PyPI distribution name).
            repo_path: Absolute path to the git repository to analyze.
                Defaults to the server's own working directory.
            include_boilerplate: Also include boilerplate members such as
                `__init__` (default: false, to reduce noise).
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
            # CLI/Actionは`Py2pumlExtractionError.friendly_message()`(日本語)を
            # そのまま出すが、MCPツールの説明文(上のdocstring)は英語で書いて
            # いる以上、エラー文言も英語にしないと自己説明的にならない
            # (「点検」で発見・修正。2026-08-29)。具象例外クラスはimportせず
            # (adapters-independence契約)、`str(error)`のテキストパターンだけを
            # 見て英語のヒントを組み立てる。CLI側の日本語ガイダンスと内容は
            # 重複するが、対象読者の言語が異なるため許容する(共有ヘルパーに
            # 括り出そうとすると、逆にadapters-independence契約に抵触する)。
            message = _build_error_message(str(error))
            raise ToolError(message) from error
        return result.json_payload

    server.add_tool(analyze_design_diff, name=TOOL_NAME, structured_output=False)
    return server
