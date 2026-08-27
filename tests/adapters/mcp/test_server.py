"""adapters/mcp/server.py のテスト。architecture.md §11。

公式Model Context Protocol Python SDK(`mcp`パッケージ)を実際に使う
(モックしない)。ComputeDesignDiffUseCase相当のフェイクを注入し、
`analyze_design_diff`ツールの引数受け渡し・エラーハンドリングだけを検証する。
"""

import asyncio
from pathlib import Path

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from design_diff.adapters.mcp.server import TOOL_NAME, create_server


class FakeResult:
    def __init__(self, json_payload: str):
        self.json_payload = json_payload


class FakeComputeUseCase:
    """ComputeDesignDiffUseCaseと同じ形を構造的に満たすフェイク。"""

    def __init__(self, json_payload: str = '{"has_changes": true}'):
        self._json_payload = json_payload
        self.calls: list[dict] = []

    def execute(self, *, base_ref, head_ref, package, include_boilerplate=False):
        self.calls.append(
            {
                "base_ref": base_ref,
                "head_ref": head_ref,
                "package": package,
                "include_boilerplate": include_boilerplate,
            }
        )
        return FakeResult(self._json_payload)


class FailingComputeUseCase:
    def __init__(self, error: Exception):
        self._error = error

    def execute(self, **kwargs):
        raise self._error


class ErrorWithFriendlyMessage(RuntimeError):
    def friendly_message(self) -> str:
        return "friendly explanation"


def call(server, arguments: dict):
    return asyncio.run(server.call_tool(TOOL_NAME, arguments))


class TestCreateServerRegistersTheTool:
    def test_registers_a_tool_named_analyze_design_diff(self):
        server = create_server(lambda repo_path: FakeComputeUseCase())

        tools = asyncio.run(server.list_tools())

        assert any(t.name == TOOL_NAME for t in tools)


class TestAnalyzeDesignDiffToolCallsUseCase:
    def test_returns_the_use_cases_json_payload_as_text_content(self):
        fake = FakeComputeUseCase(json_payload='{"has_changes": false}')
        server = create_server(lambda repo_path: fake)

        result = call(server, {"base_ref": "main", "head_ref": "feature", "package": "pkg"})

        assert result.is_error is False
        assert result.content[0].text == '{"has_changes": false}'

    def test_passes_base_ref_head_ref_package_through_to_the_use_case(self):
        fake = FakeComputeUseCase()
        server = create_server(lambda repo_path: fake)

        call(server, {"base_ref": "main", "head_ref": "feature", "package": "pkg"})

        assert fake.calls == [
            {"base_ref": "main", "head_ref": "feature", "package": "pkg", "include_boilerplate": False}
        ]

    def test_passes_include_boilerplate_through_when_true(self):
        fake = FakeComputeUseCase()
        server = create_server(lambda repo_path: fake)

        call(
            server,
            {"base_ref": "main", "head_ref": "feature", "package": "pkg", "include_boilerplate": True},
        )

        assert fake.calls[0]["include_boilerplate"] is True

    def test_repo_path_argument_is_passed_to_the_use_case_factory_as_a_path(self):
        received: list[Path | None] = []

        def factory(repo_path):
            received.append(repo_path)
            return FakeComputeUseCase()

        server = create_server(factory)

        call(
            server,
            {"base_ref": "main", "head_ref": "feature", "package": "pkg", "repo_path": "/some/repo"},
        )

        assert received == [Path("/some/repo")]

    def test_repo_path_defaults_to_none_when_omitted(self):
        received: list[Path | None] = []

        def factory(repo_path):
            received.append(repo_path)
            return FakeComputeUseCase()

        server = create_server(factory)

        call(server, {"base_ref": "main", "head_ref": "feature", "package": "pkg"})

        assert received == [None]

    def test_use_case_factory_is_called_fresh_for_every_tool_call(self):
        """MCPサーバーは1プロセス内で複数回呼び出されるため、repo_pathが呼び出し
        ごとに変わっても正しく反映される必要がある。
        """
        factory_calls: list[Path | None] = []

        def factory(repo_path):
            factory_calls.append(repo_path)
            return FakeComputeUseCase()

        server = create_server(factory)

        call(server, {"base_ref": "main", "head_ref": "feature", "package": "pkg", "repo_path": "/repo/a"})
        call(server, {"base_ref": "main", "head_ref": "feature", "package": "pkg", "repo_path": "/repo/b"})

        assert factory_calls == [Path("/repo/a"), Path("/repo/b")]


class TestAnalyzeDesignDiffToolErrorHandling:
    def test_raises_tool_error_with_friendly_message_when_available(self):
        server = create_server(lambda repo_path: FailingComputeUseCase(ErrorWithFriendlyMessage("boom")))

        with pytest.raises(ToolError) as exc_info:
            call(server, {"base_ref": "main", "head_ref": "feature", "package": "pkg"})

        assert "friendly explanation" in str(exc_info.value)

    def test_raises_tool_error_with_str_of_exception_when_no_friendly_message(self):
        server = create_server(lambda repo_path: FailingComputeUseCase(RuntimeError("plain failure")))

        with pytest.raises(ToolError) as exc_info:
            call(server, {"base_ref": "main", "head_ref": "feature", "package": "pkg"})

        assert "plain failure" in str(exc_info.value)
