#!/usr/bin/env bash
# ローカルCI。.github/workflows/ci.yml と同じ順序・同じ判定基準で実行する
# (HQ方針: privateリポジトリではGitHub Actionsが課金対象になるため、当面は
# ローカルCIで代替する。public化した時点でci.ymlがそのまま無料で動き出す想定
# なので、ci.ymlとscripts/ci.shの内容は同期させておくこと)。
#
# 使い方:
#   ./scripts/ci.sh
#
# pre-pushフックから自動実行させたい場合は scripts/install-hooks.sh を参照。
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

echo "== 0/4: Sync dependencies =="
uv sync --all-extras --dev

echo "== 1/4: Lint (ruff) =="
uv run ruff check .

echo "== 2/4: Enforce layer boundaries (import-linter) =="
uv run lint-imports

echo "== 3/4: Test with coverage =="
uv run pytest --cov --cov-report=term-missing --cov-report=xml

echo "== 4/4: Enforce domain layer coverage gate (90%) =="
uv run coverage report --include="src/design_diff/domain/*" --fail-under=90

echo "== ローカルCI: 全ステップgreen =="
