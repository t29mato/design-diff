# Changelog

このプロジェクトは [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) と
[Semantic Versioning](https://semver.org/lang/ja/) に準拠する。

## [Unreleased]

### Removed

- **skillsエコシステムへの登録をやめた(オーナー判断)。** ルートの
  `SKILL.md`・`.claude/skills/enable-design-diff/`・llms.txt/AGENTS.mdの
  `npx skills add t29mato/design-diff`関連の記述をすべて撤去した。主導線は
  MCPサーバー・README・GitHub Actionのまま(いずれも変更していない)。
  `.gitignore`の`.claude/skills/`例外も元に戻した(`.claude/`を再び丸ごと
  無視する)

HQ指示: 公開承認待ちの間のLLMO/発見可能性の仕上げ(2026-08-29)。
「既存の警告・エラーメッセージが自己説明的か点検」で、1件のバグと複数の
一貫性の欠如を発見・修正した。

### Fixed

- **PRコメントに実際に埋め込まれる画像(`--format svg`の既定、
  `GitHubStyleSvgRenderer`)に`diff.warnings`(サブモジュールのimport失敗)が
  表示されていなかったバグを修正した。** Mermaid出力のnote(§7.1で追加済み)
  は`<details>`内の折りたたまれたフォールバックに格納されているため、
  レビュアーが最初に見る画像だけでは部分解析だったことに気付けず、
  沈黙原則(『沈黙=変更なし』)を毒す抜け穴になっていた。図の一番上に
  警告バナー(⚠マーク+スキップしたモジュール名の一覧)を追加した
- 上記の実装直後、警告バナーの文言がクラスボックスの並びより横に長い場合に
  キャンバス幅が足りずテキストが切れる問題も実機検証で発見し、修正した

### Changed(自己説明性・国際的な発見可能性のための言語統一)

- **MCPツール(`analyze_design_diff`)のdocstring・エラーメッセージを英語に
  変更した。** 実装時点では日本語のままになっていたが、MCPプロトコル経由で
  任意のクライアントに公開される「公開API」である以上、READMEと同じ扱い
  (英語)にすべきという判断による
- **CLI(`design-diff`)・GitHub Action(`design-diff-action`)の`--help`
  出力(argparse)も英語に変更した。** READMEを読んで試す誰もが最初に見る
  テキストであり、同じ理由による
- 上記の新しいSVG警告バナーの文言も英語で統一した
- Mermaid出力の警告noteに、典型的な原因(依存不足の可能性)を示す短いヒントを
  追記した(モジュール名の一覧だけでは何をすべきか分からないという指摘への対応)
- `--format svg-mermaid`(旧実装)のインストール案内メッセージを、
  `--format svg`(既定・ネイティブSVG)と混同しないよう明確化した

### Notes(判断を保留した項目)

- CLI/Actionの詳細エラーガイダンス(`Py2pumlExtractionError.friendly_message()`)
  は日本語のまま残した。複数回のHQレビューを経て磨き込まれた文面であり、
  翻訳は内容変更のリスクを伴うため、今回は自己判断で書き換えず、HQの判断を
  仰ぐ対象として保留した(詳細: docs/design/architecture.md §14.6)
- README冒頭の実PRスクリーンショット・サンプルPRリンク(HQ #49で対応済み)
  ・AGENTS.mdのMCP登録手順は、既存の記載を再確認し、実装(ツール名・引数名・
  `claude mcp add`の実際のCLI構文)と一致していることを確認した。変更は不要
  だった

LLMO標準の最終ピース: design-diffのdiff機能をMCP(Model Context Protocol)の
stdioサーバーとしても公開した(HQ指示、2026-08-27)。

### Added

- **`design-diff-mcp`(新規コンソールスクリプト)**: `analyze_design_diff`と
  いう1つのツール(`base_ref`/`head_ref`/`package`/任意`repo_path`/
  `include_boilerplate` → `--format json`と同じ機械可読JSON)を公開する
  MCP stdioサーバー
- **`design_diff.mcp`(新しい最上位層、composition root)**: `cli`/`action`
  と対等な最上位層として`.importlinter`の`layers`契約に追加。既存の
  ユースケース・ポート・アダプタは無変更のまま、非破壊的な追加として実装した
  (docs/design/architecture.md §12.3で事前に見込んでいた通り)
- **`design_diff.adapters.mcp`(新しいアダプタパッケージ)**: 公式Model
  Context Protocol Python SDK(`mcp`パッケージ)への依存をここに閉じ込める。
  `adapters-independence`契約にも追加し、他のアダプタから独立させた。
  `application`層をimportせず(構造的部分型のローカルProtocolで対応)、
  他アダプタの具象例外もimportしない(`friendly_message`属性の有無を
  duck typingで判定)、という既存アダプタと同じ設計判断を踏襲した
- README(新設「MCP server」節)・AGENTS.md(新設「Part 2: Registering the
  MCP server」)に、汎用`mcp.json`・Claude Code(`claude mcp add`)・
  Claude Desktopそれぞれの登録手順を追記した

### Verification

- ユニットテスト(引数受け渡し・repo_pathの呼び出しごとの独立性・
  エラーハンドリング)、composition rootのテスト(実アダプタの配線・
  テストフックへの委譲)、実際のgit worktree・py2puml・MCP SDKを使った
  E2Eテストを追加(220 passed。ドメイン層カバレッジ100%維持)
- `uv run design-diff-mcp`を実際に起動し、エラーなくstdioで待ち受け続ける
  ことを手動でも確認した
- PyPI公開の承認とは独立に実装(公開はしていない)

### Added

- `llms.txt`を、新しい英語READMEの内容(SVGが既定の画像形式であること等)に
  合わせて全面的に更新。Capabilities節・「Notes for AI agents adopting this
  tool」節を新設
- `AGENTS.md`に「design-diffを他のリポジトリに導入する」ランブックを新設
  (対象がPythonプロジェクトか確認→`--package`名の特定→ローカル確認(任意)→
  ワークフローファイル作成→push→PRで動作確認、というエージェントが自力で
  辿れる手順)。従来の「design-diff自身への貢献」向け内容はPart 2として存置
- Claude Code用Skill `.claude/skills/enable-design-diff/SKILL.md`を新規作成。
  「このリポジトリでdesign-diffを有効化する」スキルで、対象パッケージ名の
  検出からワークフローファイル生成までを自動化する。他リポジトリで使うには
  `enable-design-diff`ディレクトリごとそのリポジトリの`.claude/skills/`へ
  コピーする

### Notes

- READMEの英語リライト(Fable実施、コミット`7b31cde`)を取り込んだ上での
  作業。README本文はこのタスクでは変更していない
- README・AGENTS.md・SKILL.mdのGitHub Actionsワークフローの例(yaml)は
  内容が同一であることを確認済み(README側のみファイルパスのコメント行が
  付いている、という差のみ)

競合調査(HQ #49。archify等のエージェントスキルが市場を証明)を受けた3タスク。

### Added

- ルートに正規の`SKILL.md`を新規作成し、`npx skills add t29mato/design-diff`
  ([vercel-labs/skills](https://github.com/vercel-labs/skills))で単一スキル
  リポジトリとして発見できるようにした(最小構成。HQ方針: 作り込まない)。
  既存の`.claude/skills/enable-design-diff/SKILL.md`は内容を維持し、両者が
  同期していることを明記(ルートが正、ネストされた方はdesign-diff自身の
  リポジトリでの直接利用向けミラー)。llms.txt/AGENTS.mdに`npx skills add`を追記
- README冒頭のヒーロー画像の直下に、実際のGitHub PR上でのコメント表示を撮った
  スクリーンショット(`docs/images/pr-comment-live-demo.png`)と、実際に触れる
  サンプルPR([#8](https://github.com/t29mato/design-diff/pull/8)。意図的に
  マージ・クローズせず開いたままにする)へのリンクを追加した。この実演のために
  `demo_shop/`(`design_diff`ツール自体からは参照されない独立したfixture
  パッケージ)と専用ワークフロー(`.github/workflows/design-diff-demo.yml`、
  `demo_shop/**`へのpathsフィルタ付き)を新設した
- READMEの`How it works`末尾に、探索・プレゼン系ツールとの違い(決定論的・
  CI強制・LLM不使用)を英語1文で追加した

README本文の変更は上記の1文追加+画像/リンクの挿入のみ(Fable承認済みの
他の文言は変更していない)。

## [0.3.0] - 2026-08-25

**目玉**: GitHub diff風のネイティブSVGレンダラーを実装し、GitHub PRコメントへの
画像埋め込みまで完成させた。**オーナー合格**(「十分達していると思います」)。
デモ図と実出力の品質比較(HQ #36)で見つかった2件の改善候補への対応から始まり、
3度の差し戻しを経てこの形に到達した。

### Changed

- Mermaid出力で、追加/削除されたリレーションの線に矢印ラベル記法
  (`ClassA <|-- ClassB : label`)で`new`/`removed`ラベルを付けるようにした。
  以前は削除されたリレーションをソースコード上のコメント(`%% removed`)で
  示していたが、これはMermaidレンダラーが描画する図には表示されない
  (ソースを直接読まない限り気付けない)ため、実際に図の中に見えるラベルに
  変更した
- **メンバー単位の増減マーカーを、行末のASCIIタグ(`[+]`/`[-]`/`[~]`)から
  行頭の絵文字マーカー(➕追加/➖削除/🔀変更)に変更した**。オーナーから
  「デモ図では追加/削除/変更したproperty・methodが視覚的に一目で分かるべき」
  という差し戻しを受け、Mermaid公式ドキュメント・GitHub issueでメンバー単位の
  スタイリングが存在しないことを一次情報で確認した上で、色の代替として絵文字を
  採用した(GitHub実機で崩れずに描画されることを確認済み)
- **削除されたメンバー行に、Unicode取り消し線合成(U+0336)でテキスト自体にも
  取り消し線を引くようにした**(➖マーカーと併用)。GitHub実機検証で、識別子・
  括弧・コロンを含む行全体に崩れず取り消し線が描画されることを確認して採用した
- JSON出力・noteの差分表記(`+`/`-`/`~`のプレーンテキスト)は変更していない。
  絵文字非対応環境向けのフォールバックとして引き続き機能する

上記の絵文字マーカー対応についても、オーナーからHQ #36/#38で再度差し戻しが
あった: 「絵文字を使うのではなく、GitHub diffみたいに視覚的にわかる形に。
Mermaidやplantumlで限界があるなら他の方法を考えて」。Mermaid classDiagramは
メンバー単位のスタイリングを一切サポートしないため(公式ドキュメント・GitHub
issueで確認済み)、**design-diff自身が直接SVGを生成するネイティブレンダラー
を新規実装した**(段階的実装。今回はレンダラー本体+README差し替えまで)。

### Added

- **`GitHubStyleSvgRenderer`を新規実装**(`adapters/rendering/
  github_style_svg_renderer.py`)。SnapshotDiffからmermaid非依存の自己完結SVGを
  直接生成する。ビジュアル仕様(GitHub diff風の配色・レイアウト)はHQが指定:
  クラスボックスのヘッダー色で状態を示し(追加=緑/削除=赤+取り消し線/変更=
  黄枠)、メンバー行はGitHubのコードdiffの行そのもの(左ガター+行全体の背景色。
  変更行は「旧シグネチャ → 新シグネチャ」を1行表示)、リレーションは矢印+
  `new`/`removed`ラベル。レイアウトは名前空間ごとの単純なグリッド配置
- `--format svg`の既定をこのネイティブレンダラーに切り替えた。旧来の
  mermaid-cli経由の変換は`--format svg-mermaid`として存置(メンバー単位の
  色分けは無い)
- README冒頭の出力例を、このSVG(`docs/images/shop-discount-codes.svg`)に
  差し替えた
- **GitHub PRコメントへのSVG画像埋め込みを実装した**(HQ #36/#38の仕上げ)。
  `AssetPort`(新規ポート)+`GitOrphanBranchAssetPublisher`
  (`adapters/github/asset_publisher.py`): 生成したSVGを`design-diff-assets`
  という専用のオーファンブランチ(mainの履歴とは無関係)へコミットし、
  `raw.githubusercontent.com/{owner}/{repo}/{コミットSHA}/assets/pr-{PR番号}.svg`
  というURLで`<img>`から参照する。URLにブランチ名ではなくコミットSHAを使うのは、
  raw.githubusercontent.comのCDNキャッシュによる更新直後の古い内容表示を
  避けるため。従来のMermaidブロックは`<details><summary>Mermaid (fallback)
  </summary>...</details>`として同じコメント内に残す(画像が読み込めない環境や
  テキストとして差分を読みたいレビュアー向け)

### Changed

- `PostDesignDiffCommentUseCase`が`svg_renderer`/`asset_port`を新たに注入
  される。沈黙する場合(変更なし かつ 警告なし)はSVGの生成・公開自体も
  行わない(不要なコミットをオーファンブランチに積み上げない)
- GitHub Actionワークフローの権限を`contents: read`→`contents: write`に変更
  (design-diff-assetsブランチへのpushに必要な最小権限。フォークPRは既存の
  if条件で引き続きスキップされる)

### Known Limitations(追加)

- ネイティブSVG(`--format svg`)には、Mermaid形式が持つ「変更クラス数が多い
  場合の上位N件表示+省略件数の要約」というサイズ制御がまだ無い。件数が非常に
  多いPRでは図が縦に長くなり続ける

実際にPRを作成し、`gh`での手動実行ではなく本物のpull_requestイベント経由で
本ワークフローが自動実行され、SVGが`design-diff-assets`ブランチにコミットされ、
コメントの`<img>`がGitHub上で実際に描画されることを確認済み。詳細は
[docs/design/architecture.md](./docs/design/architecture.md) §7.3。

## [0.2.1] - 2026-08-22

**目玉**: サブモジュールのimport失敗が無言でスキップされ、クラスが警告なしに
解析結果から消えるバグを修正した。沈黙原則(『沈黙=変更なし』)は解析が
パッケージ全体を網羅していることに依存しており、部分解析の無言化はこの
前提そのものを毒していた(v0.2.0後の追加ドッグフーディングで発見)。

### Added

- JSON出力に`warnings`配列を追加(`schema_version`を`1.0`→`1.1`に更新)。
  サブモジュールのimport失敗でスキップされたモジュール名の一覧(空なら解析は
  パッケージ全体を網羅している)
- Mermaid出力に`⚠ 解析できなかったモジュール: N件`のnoteを追加。クラス差分が
  皆無でも、警告がある限りこのnoteは出る

### Changed

- **沈黙原則の条件を変更**: 従来は`has_changes`のみで沈黙を判定していたが、
  今は`has_changes`が false **かつ** `warnings`が空の場合のみ沈黙する。
  警告がある場合はクラス差分が無くてもPRコメントを投稿し、「変更なしに
  見えるが解析は部分的だった」という事実をレビュアーに伝える
  (`PostDesignDiffCommentUseCase`)
- `SnapshotIR`に`skipped_modules`フィールドを追加し、`DiffEngine.diff()`が
  base/head双方の`skipped_modules`をマージして`SnapshotDiff.warnings`とする
  よう変更(ドメイン層)

### Fixed

- `_iter_target_classes()`がサブモジュールのimport失敗を完全に無言で
  握りつぶし(該当モジュール内の全クラスが警告もエラーも無く消える)、
  レビュアーが「変更なし」と誤認しうるバグを修正。失敗したモジュール名は
  今後`warnings`として伝播する(トップレベルの`__init__.py`自体の失敗は
  従来通り`Py2pumlExtractionError`として即座に表面化する挙動のまま)

前バージョン(v0.2.0)タグ後、PyPI公開承認待ちの間に実施した追加ドッグフーディング
(実在のPythonパッケージ10種類以上: 科学計算・Web・CLI・非同期・システム系)で
発見した3つの問題のうち、以下の2件は回避不能な既知の制約として記録するに
留めた(design-diffが対象コードの依存を自動インストールしない方針と一貫)。

### Known Limitations(追加)

- **ビルド時にファイルを生成するパッケージ(numpy等)は解析できない場合が
  ある**。`git worktree add`による生のソースチェックアウトを直接importする
  ため、ビルドシステムが生成するファイル(バージョン情報モジュール等)に
  依存するコードはimportに失敗しうる
- **広いバージョン範囲を比較する場合、base側とhead側で対象パッケージ自身の
  依存関係の要件が異なることがある**(typerで実際に確認: 新バージョンでは
  不要になった依存を、古いバージョンのコードはまだ必要としていた)

詳細は
[docs/design/investigations/real-world-package-testing.md](./docs/design/investigations/real-world-package-testing.md)
の「第2弾」と「副次的に発見した第3の問題」を参照。

## [0.2.0] - 2026-08-21

**目玉**: 属性の型解決を、py2puml本体のgetattr方式から標準ライブラリの
`typing.get_type_hints()`ベースの自前実装に変更した。これにより、importの
エイリアス(`import typing as t`)や循環import回避のための`TYPE_CHECKING`
限定importを含む実世界のPythonパッケージ(flask/click/rich/httpx)で、
以前は解析全体が失敗していたのが、正しく解析が完走するようになった。

v0.1.0タグ後、公開前に実施した実戦テスト(実在の外部Pythonパッケージ5つ+
古い未注釈コードベース1つ)で見つかった問題への対応。詳細は
[docs/design/investigations/real-world-package-testing.md](./docs/design/investigations/real-world-package-testing.md)。

### Added

- PyPI公開ワークフローの雛形(`.github/workflows/publish.yml`)。タグ(`v*`)の
  pushをトリガーにするが、実際に公開するjobはGitHub Environment `release`の
  required reviewersによる人間承認が下りるまで実行されない(Trusted Publisher/
  OIDC方式。長期APIトークンは使わない)。**このワークフローはまだ実行していない**
- Show HN下書き(`docs/marketing/show-hn-draft.md`)。**投稿はまだしていない**

### Changed

- **属性の型解決をpy2puml本体からの自前実装(`typing.get_type_hints()`ベース)に
  置き換えた**。py2pumlは型注釈を「モジュールの実行時の名前空間から`getattr()`で
  引く」方式で解決しており、importのエイリアス(`import typing as t`)や循環import
  回避のための`TYPE_CHECKING`限定importが絡むと解析全体を失敗させていた
  (実戦テストでflask/click/rich/httpxに対して実際に発生)。`typing.get_type_hints()`
  はモジュールのglobalsに対して実際に注釈を評価するため、これらのケースも正しく
  解決できる。クラスの発見(どのクラスが対象パッケージに属するか)は引き続き
  py2pumlを使うが、属性の型解決とそこから導かれる依存関係の抽出は自前実装に
  なった。1クラス・1属性ごとに例外を握りつぶし、解決できない場合はそのクラス/
  属性だけ縮退させる(解析全体は道連れにしない)

### Fixed

- クラス本体で型だけ宣言し、`__init__`で実際の値を代入する(よくあるPythonの
  イディオム)属性が、2行重複して表示されるバグを修正
  (`requests.adapters.HTTPAdapter.max_retries`で実際に発生)
- 対象コードの解析が失敗する場合(Python 3で実行できないコード、対象コード側の
  予期しない例外等)に、生の巨大なトレースバックではなく分かりやすいエラー
  メッセージを出して非ゼロ終了するようにした(CLI/GitHub Action共通)
- パッケージ内の全モジュールを解析する際に`<pkg>.__main__`をimportすると、
  ガードの無い`__main__.py`(例: `flask/__main__.py`)が実際に実行されてしまう
  バグを修正(`__main__`モジュールを解析対象から除外)
- `ModuleNotFoundError`/`ImportError`で解析が失敗した場合、design-diff自身の
  依存の問題ではなく解析対象パッケージ自身の実行時依存関係が不足している
  典型的なケースであることを案内するメッセージを追加
  (`Py2pumlExtractionError.friendly_message()`)

### Known Limitations(追加)

- **解析対象パッケージ自身の実行時依存関係が、design-diffの実行環境に
  インストールされている必要がある**(design-diff自身の依存の問題ではない。
  importベースで解析する以上避けられない性質)
- Python 3で実行できないコード(Python 2専用構文・モジュール)は解析できない
  (design-diff自体がPython 3.12+のみ対応のため)

実在のPythonパッケージ5つ(requests/flask/click/rich/httpx)に対する実戦
テストを実施し、各パッケージ自身の依存を正しくインストールした環境で
**全て解析が完走する**ことを確認済み。経緯は
[docs/design/investigations/real-world-package-testing.md](./docs/design/investigations/real-world-package-testing.md)

## [0.1.0] - 2026-08-20

初回リリース。base/head 2つのgit refから、指定したPythonパッケージのクラス構造
(クラス・継承・コンポジション依存)を抽出し、差分をMermaid classDiagramと
機械可読JSONで出力するMVP。

> **注記**: このバージョンのタグ(`v0.1.0`)は作成したが、PyPI公開・GitHub
> Release発行はいずれも行っていない。タグ作成後に実施した実戦テストで
> flask/click/rich/httpxの解析が失敗する問題が見つかり、上記の`[0.2.0]`で
> 修正した。`v0.1.0`のタグ自体は履歴として残すが、実質的にこのバージョンで
> 公開したことは無い。

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
