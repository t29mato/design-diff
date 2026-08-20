# CLAUDE.md — design-diff 開発ガイド

このファイルは、design-diff に対してコードを書く人間・AIエージェント(Claude Code含む)
向けのガイドです。プロジェクトの目的・設計方針・開発規約をまとめています。

## プロジェクトの目的

**PRレビュー時に「クラス図レベルで何が増え、何が減ったか」を自動で可視化するツールを作る。**

base↔head の2スナップショットからPythonのクラス構造(クラス・継承・コンポジション依存)を
抽出し、構造diffを取り、**Mermaid classDiagram(追加=緑 / 削除=赤 / 変更=黄)+ 機械可読JSON**
を出力する。GitHub ActionでPRコメントに自動投稿するところまでがMVP。

### なぜ作るか

AIがコードを書く時代、人間のレビューは**行diffから設計diffへ**上がる。「500行変わった」
ではなく「このクラスが増え、この依存が生えた」を見るのがレビューの本質になる、という
考えがこのプロジェクトの出発点。

### 既存ツールとの差別化(調査済み・空白地帯)

| 既存 | 粒度 | 限界 |
|---|---|---|
| codiff-action | 関数・コールグラフ | クラス・継承・依存の増減は見えない |
| griffe check | API破壊変更(テキスト) | 図として俯瞰できない |
| PyCharm "Show Diff as UML" | クラス図diff | IDE内限定。CI/PRコメントに出せない |
| pyreverse / py2puml / pymermaider | スナップショット生成のみ | diff機能がない |

**「クラス図レベルのdiffをPRに出す」ツールは現時点で存在しない。**

## 技術方針(変更する場合は根拠をdocs/design/に書くこと)

- **抽出基盤は py2puml**(https://github.com/lucsorel/py2puml)。理由: 型アノテーションから
  **継承+コンポジション依存**を抽出でき、pyreverseより依存関係の質が良い。
- **実装言語は Python**。py2pumlがPythonライブラリであり、対象コードと同じ環境で解析する
  必要があるため。
- **パッケージ管理・実行は uv**。`uv init` / `uv add` / `uv run` を使う。requirements.txtや
  poetryは使わない。CIでも `uv sync` / `uv run` を使うこと。
- py2puml をライブラリとして組み込めない場合(内部APIが不安定等)は、PlantUML出力の
  パースにフォールバックしてよい。実際に検証したうえで採否を決め、根拠を
  `docs/design/architecture.md` に書くこと(§5に検証結果あり)。
- 型アノテーションの無いコードでは依存が出ない、という制約はREADMEに正直に明記する
  (=アノテーション文化を促進するツールでもある、と割り切る)。

## MVPスコープ

1. **CLI**: `design-diff diff <base_ref> <head_ref> --package <pkg>` → Mermaid classDiagram
   + JSON出力。2スナップショットは git worktree で展開して比較する。
2. **GitHub Action**: PRイベントでdiffを取りコメント投稿(初回作成・push毎に同じコメントを
   更新・構造変化がなければ沈黙 = codiff-action方式)。
3. **LLMO標準装備**: JSON出力モード、README冒頭に機械可読な1文、`AGENTS.md` / `SKILL.md`、
   将来のMCPサーバー化を見据えたインターフェース。**AIレビュアーが設計レビューに使える
   こと**が主要な配布チャネルの一つになる。

## 設計・品質方針(必須)

- **設計ファースト**: 大きめの変更(アーキテクチャに関わるもの・技術選定の変更)は、
  実装着手前に `docs/design/` にクラス図レベルの設計(Mermaid classDiagram)と依存方向の
  説明を書き、レビュー・議論を経てから実装に進むこと。
- **クリーンアーキテクチャ**: ドメイン層(構造の中間表現・diffアルゴリズム)は
  py2puml・git・GitHub API・出力形式に依存しない。抽出はアダプタ層に隔離し、**将来
  pyreverse や AST直読みのバックエンドを差し替えられる構造**にする(py2puml依存を
  閉じ込める)。レンダラ(Mermaid/JSON)も同様にアダプタ。レイヤー構成の詳細は
  `docs/design/architecture.md` を参照。
- **TDD**: テスト先行。ドメイン層(中間表現・diff)のカバレッジ目標 **90%**。
- **依存方向の機械的強制**: `import-linter` をCIに組み込み、レイヤー違反でCIを落とす。
  設定を緩めてはならない(緩める場合は理由をdocs/design/に書き、レビューを経ること)。
- **ドッグフーディング**: このツール自身のPRに design-diff を掛ける。自分の設計diffが
  読めない出力は失格。

## CI

- CIは `.github/workflows/ci.yml`(ruff → import-linter → pytest+カバレッジ →
  ドメイン層カバレッジ90%ゲート)。
- リポジトリがprivateの間はGitHub Actionsの代わりに `scripts/ci.sh` でローカルCIを回す
  (`.github/workflows/ci.yml` と同じ判定基準)。`scripts/install-hooks.sh` を実行すると
  pre-pushフックとして自動化できる。詳細はREADMEを参照。
- self-hosted runnerは使わない(理由は `docs/design/architecture.md` §13)。

## ブランチ・タグ運用

- mainへの直接コミット・pushは許可されている(小規模な初期段階のプロジェクトのため)。
- push前に必ずローカルでテスト・lint・import-linterがgreenであることを確認する
  (`scripts/ci.sh` を実行すればよい)。
- タグ・GitHub Release・PyPI公開・破壊的なCI設定緩和には、メンテナの承認が必要。
- Show HN・SNS投稿などの外部発信は下書きにとどめ、自動で投稿しないこと。

## AIエージェントへの補足

- lintの機械的な修正・テストログの要約・README/リリースノートの下書きのような単純作業は、
  対応できる環境であれば軽量なサブエージェント/モデルに委譲してよい。設計判断は委譲しない。
- 判断に迷う設計変更(技術選定・レイヤー構成の変更など)は、実装を進める前に
  `docs/design/` に検討内容を書き、レビューを経ること。
