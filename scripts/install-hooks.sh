#!/usr/bin/env bash
# .githooks/ 配下のフックを有効化する。
#
# .git/hooks はリポジトリに含まれずクローンした人には共有されないため、
# `git config core.hooksPath` でリポジトリ管理下の .githooks/ を指すようにする。
# これにより pre-push フック(scripts/ci.sh を実行する)が有効になる。
#
# 使い方(クローン後に一度だけ実行):
#   ./scripts/install-hooks.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

chmod +x .githooks/pre-push
git config core.hooksPath .githooks

echo "core.hooksPath を .githooks に設定しました。"
echo "以後、git push 前に scripts/ci.sh が自動実行されます。"
echo "(一時的に無効化したい場合は: git push --no-verify)"
