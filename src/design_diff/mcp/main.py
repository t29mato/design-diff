"""design-diff MCP(Model Context Protocol)サーバーのエントリポイント。

architecture.md §11。`analyze_design_diff`というツールとして、design-diffの
diff機能をstdio経由で公開する。cli/main.py・action/main.pyと同じ「引数解析と
アダプタの注入だけを行う薄い殻」の方針(HQ指摘2)。

`design_diff.mcp`はcli/actionと同じ最上位層(composition root)であり、
import-linterの`layers`契約でcli/actionと対等(相互に独立)に扱う。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from design_diff.adapters.extraction.py2puml_extractor import Py2pumlExtractor
from design_diff.adapters.mcp.server import create_server
from design_diff.adapters.rendering.json_renderer import JsonRenderer
from design_diff.adapters.rendering.mermaid_renderer import MermaidRenderer
from design_diff.adapters.vcs.git_worktree import GitWorktreeVcs
from design_diff.application.use_cases.compute_design_diff import ComputeDesignDiffUseCase

UseCaseFactory = Callable[[Path | None], ComputeDesignDiffUseCase]


def _default_use_case_factory(repo_path: Path | None) -> ComputeDesignDiffUseCase:
    return ComputeDesignDiffUseCase(
        vcs=GitWorktreeVcs(repo_path=repo_path),
        extractor=Py2pumlExtractor(),
        mermaid_renderer=MermaidRenderer(),
        json_renderer=JsonRenderer(),
    )


def main(
    use_case_factory: UseCaseFactory = _default_use_case_factory,
    run_server: Callable[[object], None] | None = None,
) -> None:
    """MCPサーバーを組み立ててstdioで待ち受ける。

    `run_server`はテスト用のフック(既定ではNone。その場合`server.run(
    transport="stdio")`を呼ぶ。テストではブロッキングを避けるため、サーバー
    オブジェクトを受け取って何もしない/検査するだけのフェイクを注入する)。
    """
    server = create_server(use_case_factory)
    if run_server is not None:
        run_server(server)
    else:
        server.run(transport="stdio")


if __name__ == "__main__":
    main()
