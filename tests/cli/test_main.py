"""CLIのテスト。architecture.md §2, §8: CLIは引数解析とアダプタ注入だけの薄い殻。

- ユニットテスト: フェイクのuse_case_factoryを注入し、ロジック(引数解析・出力選択)だけを検証
- 統合テスト: 実際のgit worktree・py2pumlを使ったエンドツーエンド(MVP完成の証明)
"""

import json
import subprocess
from pathlib import Path

import pytest

from design_diff.adapters.rendering.svg_renderer import SvgRenderingUnavailableError
from design_diff.application.use_cases.compute_design_diff import DesignDiffResult
from design_diff.cli.main import main
from design_diff.domain.diff import ClassDiff, RelationDiff, SnapshotDiff


class FakeUseCase:
    def __init__(self, result: DesignDiffResult):
        self._result = result
        self.calls: list[tuple] = []

    def execute(
        self, base_ref: str, head_ref: str, package: str, *, include_dunder: bool = False
    ) -> DesignDiffResult:
        self.calls.append((base_ref, head_ref, package, include_dunder))
        return self._result


CANNED_RESULT = DesignDiffResult(
    diff=SnapshotDiff(classes=ClassDiff(), relations=RelationDiff()),
    mermaid="classDiagram\n    %% canned",
    json_payload=json.dumps({"schema_version": "1.0", "has_changes": False}),
)


class TestCliDiffCommandWiring:
    def test_prints_mermaid_by_default(self, capsys):
        fake_use_case = FakeUseCase(CANNED_RESULT)

        exit_code = main(
            ["diff", "main", "feature", "--package", "pkg"],
            use_case_factory=lambda repo_path: fake_use_case,
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out.strip() == CANNED_RESULT.mermaid
        assert fake_use_case.calls == [("main", "feature", "pkg", False)]

    def test_prints_json_when_format_json(self, capsys):
        fake_use_case = FakeUseCase(CANNED_RESULT)

        main(
            ["diff", "main", "feature", "--package", "pkg", "--format", "json"],
            use_case_factory=lambda repo_path: fake_use_case,
        )

        captured = capsys.readouterr()
        assert captured.out.strip() == CANNED_RESULT.json_payload

    def test_missing_package_argument_is_a_usage_error(self):
        with pytest.raises(SystemExit):
            main(["diff", "main", "feature"], use_case_factory=lambda repo_path: FakeUseCase(CANNED_RESULT))

    def test_repo_argument_is_passed_to_use_case_factory(self):
        received_repo_paths = []

        def factory(repo_path):
            received_repo_paths.append(repo_path)
            return FakeUseCase(CANNED_RESULT)

        main(
            ["diff", "main", "feature", "--package", "pkg", "--repo", "/some/repo"],
            use_case_factory=factory,
        )

        assert received_repo_paths == [Path("/some/repo")]

    def test_format_svg_prints_svg_produced_by_svg_renderer(self, capsys):
        class FakeSvgRenderer:
            def render(self, mermaid_text: str) -> str:
                assert mermaid_text == CANNED_RESULT.mermaid
                return "<svg>fake</svg>"

        exit_code = main(
            ["diff", "main", "feature", "--package", "pkg", "--format", "svg"],
            use_case_factory=lambda repo_path: FakeUseCase(CANNED_RESULT),
            svg_renderer_factory=FakeSvgRenderer,
        )

        captured = capsys.readouterr()
        assert exit_code == 0
        assert captured.out.strip() == "<svg>fake</svg>"

    def test_format_svg_prints_actionable_error_and_exits_nonzero_when_unavailable(self, capsys):
        class UnavailableSvgRenderer:
            def render(self, mermaid_text: str) -> str:
                raise SvgRenderingUnavailableError("mermaid-cliが見つかりません。npm install ...")

        exit_code = main(
            ["diff", "main", "feature", "--package", "pkg", "--format", "svg"],
            use_case_factory=lambda repo_path: FakeUseCase(CANNED_RESULT),
            svg_renderer_factory=UnavailableSvgRenderer,
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "npm install" in captured.err

    def test_include_dunder_flag_defaults_to_false(self, capsys):
        fake_use_case = FakeUseCase(CANNED_RESULT)

        main(
            ["diff", "main", "feature", "--package", "pkg"],
            use_case_factory=lambda repo_path: fake_use_case,
        )

        assert fake_use_case.calls[0][3] is False

    def test_include_dunder_flag_can_be_enabled(self, capsys):
        fake_use_case = FakeUseCase(CANNED_RESULT)

        main(
            ["diff", "main", "feature", "--package", "pkg", "--include-dunder"],
            use_case_factory=lambda repo_path: fake_use_case,
        )

        assert fake_use_case.calls[0][3] is True


def run_git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


@pytest.fixture
def git_repo_with_package(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    run_git(repo, "init", "-q")
    run_git(repo, "config", "user.email", "test@example.com")
    run_git(repo, "config", "user.name", "Test")

    pkg = repo / "cli_e2e_pkg"
    pkg.mkdir()
    (pkg / "__init__.py").touch()
    (pkg / "models.py").write_text(
        "class Vehicle:\n"
        "    def __init__(self, name: str):\n"
        "        self.name: str = name\n"
    )
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "initial")
    run_git(repo, "branch", "-m", "main")

    run_git(repo, "checkout", "-q", "-b", "feature")
    (pkg / "models.py").write_text(
        "class Vehicle:\n"
        "    def __init__(self, name: str):\n"
        "        self.name: str = name\n"
        "\n"
        "\n"
        "class Car(Vehicle):\n"
        "    pass\n"
    )
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-q", "-m", "add Car")
    run_git(repo, "checkout", "-q", "main")

    return repo


class TestCliEndToEnd:
    """MVP完成の証明: 実際のgit worktree + py2pumlを使ったエンドツーエンド。"""

    def test_diff_json_end_to_end_detects_added_class(self, git_repo_with_package, capsys):
        exit_code = main(
            [
                "diff",
                "main",
                "feature",
                "--package",
                "cli_e2e_pkg",
                "--format",
                "json",
                "--repo",
                str(git_repo_with_package),
            ]
        )

        captured = capsys.readouterr()
        payload = json.loads(captured.out)

        assert exit_code == 0
        assert payload["has_changes"] is True
        added_fqns = [c["fqn"] for c in payload["classes"]["added"]]
        assert "cli_e2e_pkg.models.Car" in added_fqns

    def test_diff_mermaid_end_to_end_detects_added_class(self, git_repo_with_package, capsys):
        main(
            [
                "diff",
                "main",
                "feature",
                "--package",
                "cli_e2e_pkg",
                "--repo",
                str(git_repo_with_package),
            ]
        )

        captured = capsys.readouterr()
        # fqnそのものではなく短いラベル + namespace記法で出力される(HQフィードバック)
        assert 'class cli_e2e_pkg_models_Car["[+] Car"]' in captured.out
        assert "namespace cli_e2e_pkg.models {" in captured.out
