"""design_diff.mcp.main のテスト。architecture.md §2, §11: MCPサーバーの
composition rootは引数解析とアダプタ注入だけの薄い殻(cli/main.py・
action/main.pyと同じ方針)。

- ユニットテスト: フェイクのuse_case_factory・run_serverフックを注入し、
  ロジック(サーバー組み立て・実行委譲)だけを検証
- 統合テスト: 実際のgit worktree・py2puml・MCP SDKを使ったエンドツーエンド
"""

import asyncio
import json
import subprocess
from pathlib import Path

import pytest

from design_diff.adapters.mcp.server import TOOL_NAME
from design_diff.mcp.main import _default_use_case_factory, main


class TestMcpMainWiring:
    def test_builds_a_server_and_delegates_to_run_server_hook(self):
        received_servers = []

        def fake_use_case_factory(repo_path):
            class FakeUseCase:
                def execute(self, **kwargs):
                    raise AssertionError("not called in this test")

            return FakeUseCase()

        def fake_run_server(server):
            received_servers.append(server)

        main(use_case_factory=fake_use_case_factory, run_server=fake_run_server)

        assert len(received_servers) == 1
        tools = asyncio.run(received_servers[0].list_tools())
        assert any(t.name == TOOL_NAME for t in tools)

    def test_default_run_server_calls_run_with_stdio_transport(self):
        """既定(run_server未指定)ではserver.run(transport="stdio")が呼ばれること
        を、run自体をフェイクに差し替えて確認する(実際のstdio待受はしない)。
        """
        calls = []

        class FakeServer:
            def run(self, transport):
                calls.append(transport)

        def use_case_factory(repo_path):
            raise AssertionError("not called in this test")

        import design_diff.mcp.main as mcp_main

        original_create_server = mcp_main.create_server
        mcp_main.create_server = lambda factory: FakeServer()
        try:
            main(use_case_factory=use_case_factory)
        finally:
            mcp_main.create_server = original_create_server

        assert calls == ["stdio"]


class TestDefaultUseCaseFactory:
    """既定のcomposition rootが、実際のアダプタを正しく配線していること。"""

    def test_wires_the_real_adapters(self):
        from design_diff.adapters.extraction.py2puml_extractor import Py2pumlExtractor
        from design_diff.adapters.rendering.json_renderer import JsonRenderer
        from design_diff.adapters.rendering.mermaid_renderer import MermaidRenderer
        from design_diff.adapters.vcs.git_worktree import GitWorktreeVcs
        from design_diff.application.use_cases.compute_design_diff import ComputeDesignDiffUseCase

        use_case = _default_use_case_factory(Path("/some/repo"))

        assert isinstance(use_case, ComputeDesignDiffUseCase)
        assert isinstance(use_case._vcs, GitWorktreeVcs)
        assert isinstance(use_case._extractor, Py2pumlExtractor)
        assert isinstance(use_case._mermaid_renderer, MermaidRenderer)
        assert isinstance(use_case._json_renderer, JsonRenderer)


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo_with_package(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test")

    pkg = repo / "mcp_e2e_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").touch()
    (pkg / "models.py").write_text(
        "class Vehicle:\n    def __init__(self, name: str):\n        self.name: str = name\n"
    )
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "initial")
    run_git(repo, "branch", "-m", "main")

    run_git(repo, "checkout", "-q", "-b", "feature")
    (pkg / "models.py").write_text(
        "class Vehicle:\n"
        "    def __init__(self, name: str):\n"
        "        self.name: str = name\n"
        "\n\n"
        "class Car(Vehicle):\n"
        "    pass\n"
    )
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "add Car")
    run_git(repo, "checkout", "-q", "main")

    return repo


class TestMcpEndToEnd:
    """MCPサーバー統合の証明: 実際のgit worktree + py2puml + MCP SDKを使った
    エンドツーエンド(HQ指示: MCPサーバー化の受け入れ基準)。
    """

    def test_analyze_design_diff_tool_detects_added_class_via_real_mcp_server(self, git_repo_with_package):
        from design_diff.adapters.mcp.server import create_server

        server = create_server(lambda repo_path: _default_use_case_factory(repo_path))

        result = asyncio.run(
            server.call_tool(
                TOOL_NAME,
                {
                    "base_ref": "main",
                    "head_ref": "feature",
                    "package": "mcp_e2e_pkg",
                    "repo_path": str(git_repo_with_package),
                },
            )
        )

        payload = json.loads(result.content[0].text)
        assert result.is_error is False
        assert payload["has_changes"] is True
        assert [c["name"] for c in payload["classes"]["added"]] == ["Car"]
