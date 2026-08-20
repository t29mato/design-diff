"""GitHub Actionエントリポイントのテスト。architecture.md §2, §8: 引数解析と
アダプタ注入だけの薄い殻。CLIと同じ方針。
"""

from design_diff.action.main import main
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

        from pathlib import Path

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
