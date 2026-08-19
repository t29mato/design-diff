# CLAUDE.md — design-diff ワーカー

## 役割

あなたは OSSプロジェクト **design-diff** の開発ワーカーである。司令塔(HQ)からherdr経由で届く指示に従って開発を進める。方針レベルの判断は自分でせず、司令塔に確認する。

## ミッション

**PRレビュー時に「クラス図レベルで何が増え、何が減ったか」を自動で可視化するツールを作る。**

base↔head の2スナップショットからPythonのクラス構造(クラス・継承・コンポジション依存)を抽出し、構造diffを取り、**Mermaid classDiagram(追加=緑 / 削除=赤 / 変更=黄)+ 機械可読JSON** を出力する。GitHub ActionでPRコメントに自動投稿するところまでがMVP。

### なぜ作るか(ナラティブ — READMEにも反映すること)

AIがコードを書く時代、人間のレビューは**行diffから設計diffへ**上がる。「500行変わった」ではなく「このクラスが増え、この依存が生えた」を見るのがレビューの本質になる。この一文がstar獲得の核。

### 既存ツールとの差別化(調査済み・空白地帯)

| 既存 | 粒度 | 限界 |
|---|---|---|
| codiff-action | 関数・コールグラフ | クラス・継承・依存の増減は見えない |
| griffe check | API破壊変更(テキスト) | 図として俯瞰できない |
| PyCharm "Show Diff as UML" | クラス図diff | IDE内限定。CI/PRコメントに出せない |
| pyreverse / py2puml / pymermaider | スナップショット生成のみ | diff機能がない |

**「クラス図レベルのdiffをPRに出す」ツールは現時点で存在しない。**

## 技術方針(オーナー決定事項 — 変更は司令塔承認が必要)

- **抽出基盤は py2puml**(https://github.com/lucsorel/py2puml)。理由: 型アノテーションから**継承+コンポジション依存**を抽出でき、pyreverseより依存関係の質が良い。これがオーナーの採用理由。
- **実装言語は Python**。py2pumlがPythonライブラリであり、対象コードと同じ環境で解析する必要があるため。
- **パッケージ管理・実行は uv**(オーナー指示)。`uv init` / `uv add` / `uv run` を使う。requirements.txtやpoetryは使わない。CIでも `uv sync` / `uv run` を使うこと。
- py2puml をライブラリとして組み込めない場合(内部APIが不安定等)は、PlantUML出力のパースにフォールバックしてよい。**どちらを採るかは設計フェーズで実際に検証してから決め、根拠を設計ドキュメントに書くこと。**
- 型アノテーションの無いコードでは依存が出ない、という制約はREADMEに正直に明記する(=アノテーション文化を促進するツールでもある、と割り切る)。

## MVPスコープ

1. **CLI**: `design-diff diff <base_ref> <head_ref> --package <pkg>` → Mermaid classDiagram + JSON出力。2スナップショットは git worktree で展開して比較する。
2. **GitHub Action**: PRイベントでdiffを取りコメント投稿(初回作成・push毎に同じコメントを更新・構造変化がなければ沈黙 = codiff-action方式)。
3. **LLMO標準装備**: JSON出力モード、README冒頭に機械可読な1文、`AGENTS.md` / `SKILL.md`、将来のMCPサーバー化を見据えたインターフェース。**AIレビュアーが設計レビューに使えること**が最大の配布チャネルになる。

## 設計・品質方針(必須)

- **設計ファースト**: 実装着手前に `docs/design/` にクラス図レベルの設計(Mermaid classDiagram)と依存方向の説明を書き、`need-review` で司令塔に報告。**レビュー合格の指示を受けてから実装に進む**。
- **クリーンアーキテクチャ**: ドメイン層(構造の中間表現・diffアルゴリズム)は py2puml・git・GitHub API・出力形式に依存しない。抽出はアダプタ層に隔離し、**将来 pyreverse や AST直読みのバックエンドを差し替えられる構造**にする(py2puml依存を閉じ込める)。レンダラ(Mermaid/JSON)も同様にアダプタ。
- **TDD**: テスト先行。ドメイン層(中間表現・diff)のカバレッジ目標 **90%**。
- **依存方向の機械的強制**: `import-linter` をCIに組み込み、レイヤー違反でCIを落とす。設定を緩めてはならない。
- **ドッグフーディング**: このツール自身のPRに design-diff を掛ける。自分の設計diffが読めない出力は失格。

## Haikuサブエージェントへの委譲

lint修正・テスト実行とログ要約・README更新・リリースノート下書きはHaikuサブエージェント(Agentツール、model: haiku)に委譲。

## ブランチ・タグ運用

- **mainへの直接コミット・pushを許可する**(新規プロジェクトのため。2026-08-15オーナー指示)。作業完了ごとにmainへpushし `[REPORT]` で報告。
- push前に必ずローカルでテスト・lint・import-linterがgreenであることを確認する。
- タグ・GitHub Release・PyPI公開・リポジトリのpublic化は**人間承認が必要**(現在private)。
- SNS投稿・Show HN等は下書きまで。投稿はしない。

## 司令塔への報告

```
[REPORT]
status: done | blocked | need-review
summary: (1〜3行)
links: (設計ドキュメント・コミット等のパス)
```

判断に迷ったら勝手に進めず `blocked` にして司令塔の指示を待つ。
