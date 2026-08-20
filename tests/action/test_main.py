"""GitHub Actionエントリポイントのテスト。architecture.md §2, §8: 引数解析と
アダプタ注入だけの薄い殻。CLIと同じ方針。
"""

from pathlib import Path

from design_diff.action.main import ActionConfig, main, parse_config
from design_diff.adapters.extraction.py2puml_extractor import Py2pumlExtractionError
from design_diff.application.use_cases.compute_design_diff import DesignDiffResult
from design_diff.domain.diff import ClassDiff, RelationDiff, SnapshotDiff
from design_diff.domain.model import ClassIR


class FakeUseCase:
    def __init__(self, result: DesignDiffResult):
        self._result = result
        self.calls: list[tuple] = []

    def execute(self, pr, base_ref, head_ref, package, *, include_dunder=False):
        self.calls.append((pr, base_ref, head_ref, package, include_dunder))
        return self._result


CANNED_RESULT_WITH_CHANGES = DesignDiffResult(
    diff=SnapshotDiff(
        classes=ClassDiff(added=(ClassIR(fqn="pkg.Battery", name="Battery"),)), relations=RelationDiff()
    ),
    mermaid="classDiagram\n    class pkg_Battery",
    json_payload='{"has_changes": true}',
)


class TestActionMain:
    def test_parses_args_and_calls_use_case_with_expected_values(self):
        fake_use_case = FakeUseCase(CANNED_RESULT_WITH_CHANGES)

        exit_code = main(
            [
                "main",
                "feature",
                "--package",
                "pkg",
                "--pr",
                "42",
                "--repo",
                "owner/repo",
            ],
            use_case_factory=lambda repo_path, repo_slug: fake_use_case,
        )

        assert exit_code == 0
        assert fake_use_case.calls == [(42, "main", "feature", "pkg", False)]

    def test_passes_repo_path_and_repo_slug_to_the_use_case_factory(self):
        received = []

        def factory(repo_path, repo_slug):
            received.append((repo_path, repo_slug))
            return FakeUseCase(CANNED_RESULT_WITH_CHANGES)

        main(
            [
                "main",
                "feature",
                "--package",
                "pkg",
                "--pr",
                "1",
                "--repo",
                "owner/repo",
                "--repo-path",
                "/some/repo",
            ],
            use_case_factory=factory,
        )

        assert received == [(Path("/some/repo"), "owner/repo")]

    def test_include_dunder_flag_is_passed_through(self):
        fake_use_case = FakeUseCase(CANNED_RESULT_WITH_CHANGES)

        main(
            [
                "main",
                "feature",
                "--package",
                "pkg",
                "--pr",
                "1",
                "--repo",
                "owner/repo",
                "--include-dunder",
            ],
            use_case_factory=lambda repo_path, repo_slug: fake_use_case,
        )

        assert fake_use_case.calls[0][4] is True

    def test_prints_json_payload_for_logs(self, capsys):
        fake_use_case = FakeUseCase(CANNED_RESULT_WITH_CHANGES)

        main(
            ["main", "feature", "--package", "pkg", "--pr", "1", "--repo", "owner/repo"],
            use_case_factory=lambda repo_path, repo_slug: fake_use_case,
        )

        captured = capsys.readouterr()
        assert captured.out.strip() == CANNED_RESULT_WITH_CHANGES.json_payload

    def test_extraction_failure_prints_actionable_error_and_exits_nonzero(self, capsys):
        """cli/main.pyと同じ回帰対応。PRのコードがモジュールレベルで実行時
        コンテキスト依存のオブジェクトにアクセスしていると解析全体が失敗しうる。
        Actionのログに生の巨大なトレースバックではなく分かりやすい説明を残す。
        """

        class FailingUseCase:
            def execute(self, pr, base_ref, head_ref, package, *, include_dunder=False):
                raise Py2pumlExtractionError("py2puml worker failed for path=... : RuntimeError: ...")

        exit_code = main(
            ["main", "feature", "--package", "pkg", "--pr", "1", "--repo", "owner/repo"],
            use_case_factory=lambda repo_path, repo_slug: FailingUseCase(),
        )

        captured = capsys.readouterr()
        assert exit_code == 1
        assert "解析中にエラーが発生しました" in captured.err


class TestParseConfig:
    """argparse.NamespaceではなくActionConfig(型付きの値オブジェクト)を組み立てる。

    生のNamespaceを引き回すと属性名の綴りミスが実行時までわからない。
    値オブジェクトにすることで、呼び出し側(main())が扱うデータの形を
    ドメイン層と同じように明示できる。
    """

    def test_builds_an_action_config_from_parsed_args(self):
        config = parse_config(
            ["main", "feature", "--package", "pkg", "--pr", "42", "--repo", "owner/repo"]
        )

        assert config == ActionConfig(
            base_ref="main",
            head_ref="feature",
            package="pkg",
            pr=42,
            repo="owner/repo",
            repo_path=None,
            include_dunder=False,
        )

    def test_builds_an_action_config_with_optional_fields_set(self):
        config = parse_config(
            [
                "main",
                "feature",
                "--package",
                "pkg",
                "--pr",
                "1",
                "--repo",
                "owner/repo",
                "--repo-path",
                "/some/repo",
                "--include-dunder",
            ]
        )

        assert config.repo_path == Path("/some/repo")
        assert config.include_dunder is True
