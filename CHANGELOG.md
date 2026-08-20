# Changelog

このプロジェクトは [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) と
[Semantic Versioning](https://semver.org/lang/ja/) に準拠する。

## [Unreleased]

v0.1.0タグ後、公開前に実施した実戦テスト(実在の外部Pythonパッケージ5つ+
古い未注釈コードベース1つ)で見つかった問題への対応。詳細は
[docs/design/investigations/real-world-package-testing.md](./docs/design/investigations/real-world-package-testing.md)。

### Fixed

- クラス本体で型だけ宣言し、`__init__`で実際の値を代入する(よくあるPythonの
  イディオム)属性が、py2pumlの挙動により2行重複して表示されるバグを修正
  (`requests.adapters.HTTPAdapter.max_retries`で実際に発生)
- 対象コードの解析がpy2puml本体の制約で失敗する場合(実行時コンテキスト依存の
  オブジェクトへのアクセス、importのエイリアス、循環import回避のための
  TYPE_CHECKING限定importのいずれか)に、生の巨大なトレースバックではなく
  分かりやすいエラーメッセージを出して非ゼロ終了するようにした
  (CLI/GitHub Action共通)

### Known Limitations(追加)

- 型注釈が豊富な現代的なパッケージほど、py2puml本体の型注釈解決ロジックの
  制約に触れやすい(実戦テストでrequests以外の4/5パッケージが解析失敗)。
  真因は最小再現コードまで絞り込んで検証済み(詳細は
  [docs/design/investigations/py2puml-resolution-failures-root-cause.md](./docs/design/investigations/py2puml-resolution-failures-root-cause.md))。
  クラッシュ・無限ループ・異常な長時間実行にはならないことは確認済み

## [0.1.0] - 2026-08-20

初回リリース。base/head 2つのgit refから、指定したPythonパッケージのクラス構造
(クラス・継承・コンポジション依存)を抽出し、差分をMermaid classDiagramと
機械可読JSONで出力するMVP。

### Added

- `design-diff diff <base_ref> <head_ref> --package <pkg>` CLI(`--format
  mermaid|json|svg`)。2スナップショットはgit worktreeで展開して比較する
- クラスの追加/削除/変更、継承・コンポジション依存の増減を検出するdiffエンジン
- Mermaid classDiagramレンダラー:
  - 追加/削除/変更クラスをASCIIステータスタグ(`[+]`/`[-]`/`[~]`)と`style`文
    (追加=緑/削除=赤/変更=黄、背景・枠線・文字色)の両方で示す
  - 変更されたクラスは、増減した属性/メソッドをメンバー行自体にもASCIIタグで
    直接示す(型変更時は`(was: <旧の型>)`も付記)
  - 可視性マーカー(`+`/`-`)、モジュールパスによる`namespace`グループ化、
    図のサイズ制御(既定20クラスを超えたら影響度順の上位N件のみ表示)
- JSON出力(LLMO): AIレビュアーがそのまま読める自己完結フォーマット。
  `mermaid`フィールドにレンダリング済みのMermaidブロックも同梱
- GitHub Action(`.github/workflows/design-diff-comment.yml`): PRのopen/更新
  ごとに設計diffを計算し、コメントとしてupsert投稿する。構造変化が無いPRでは
  沈黙する。フォークPRは`pull_request_target`を使わずスキップし、シークレットも
  渡さない
- ローカルSVG出力(`--format svg`、mermaid-cli利用。重い依存は自動導入しない)
- MITライセンス

### Known Limitations

- 型アノテーションが無いコードでは依存(継承・コンポジション)が検出できない
- リネーム検出・Enum専用の表現・多言語(Python以外)対応は範囲外
- Mermaidの`classDiagram`はメンバー(property/method)単位の色付けに対応して
  いない(Mermaid本体の構造的制約。詳細はREADME「表示に関する注記」参照)
