# AGENTS.md

design-diff にコード変更を加えるAIコーディングエージェント向けの手順。
プロジェクトの背景・設計方針は [CLAUDE.md](./CLAUDE.md) と
[docs/design/architecture.md](./docs/design/architecture.md) を参照。

## セットアップ

```bash
uv sync --dev
```

`uv` (https://docs.astral.sh/uv/) を使う。`pip`/`poetry`/`requirements.txt` は使わない。

## ビルド・テスト・Lint

push前に必ずこれを実行し、全ステップgreenであることを確認する:

```bash
./scripts/ci.sh
```

内訳(`.github/workflows/ci.yml` と同一の判定基準):

```bash
uv run ruff check .                                                          # lint
uv run lint-imports                                                          # レイヤー境界の強制
uv run pytest --cov --cov-report=term-missing --cov-report=xml               # テスト+カバレッジ
uv run coverage report --include="src/design_diff/domain/*" --fail-under=90  # ドメイン層カバレッジ90%ゲート
```

クローン後に一度 `./scripts/install-hooks.sh` を実行すると、`git push` のたびに
上記が自動実行される(pre-pushフック)。

## コード規約

- **クリーンアーキテクチャ**: `domain`(純粋なIR+diffアルゴリズム。py2puml/git/GitHub
  APIに一切依存しない)→ `application`(Protocolベースのport + use case)→
  `adapters`(py2puml抽出・git worktree・Mermaid/JSON/GitHub diff風ネイティブSVG
  レンダリング・GitHubコメント投稿・design-diff-assetsブランチへのSVGアセット
  公開)→ `cli`/`action`(composition root)。依存方向は
  `cli|action → application → adapters → domain` のみ
- **import-linterの4契約を緩めない**(`.importlinter`)。レイヤー違反でCIが落ちる
  設計は意図的なもので、緩和にはメンテナの承認が必要
- **TDD**: テスト先行。`domain`層のカバレッジ目標90%(CIのゲートで強制)
- 型アノテーションは必須(design-diff自身がpy2puml経由で型アノテーションから
  依存関係を抽出するツールであり、自分自身がその模範であるべきため)

## 設計変更の進め方

アーキテクチャに関わる変更・技術選定の変更は、実装着手前に
`docs/design/` にクラス図レベルの設計(Mermaid classDiagram)と依存方向の説明を
書くこと。スパイク・調査だけの場合は `docs/design/spikes/`(検証後に削除する
前提)または `docs/design/investigations/`(恒久的な記録)に置く。

## コミット・ブランチ

- mainへの直接コミット・pushは許可されている(小規模な初期段階のプロジェクトの
  ため)。push前に `./scripts/ci.sh` がgreenであることを確認する
- タグ・GitHub Release・PyPI公開・破壊的なCI設定緩和には、人間のメンテナの
  承認が必要。エージェントが単独で実行してはならない

## このツール自身の使い方(ドッグフーディング)

自分のPRに対してdesign-diffを掛けて、設計diffが読めるか確認すること:

```bash
uv run design-diff diff main <your-branch> --package design_diff --format mermaid
```

画像として確認したい場合(GitHub diff風のネイティブSVG。PRコメントで実際に
使われる形式)は `--format svg > diagram.svg` でファイルに出力してから開く。

出力例は [docs/examples/](./docs/examples/) を参照。
