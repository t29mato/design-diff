# Changelog

このプロジェクトは [Keep a Changelog](https://keepachangelog.com/ja/1.1.0/) と
[Semantic Versioning](https://semver.org/lang/ja/) に準拠する。

## [Unreleased]

デモ図と実出力の品質比較(HQ #36。結論: 同等以上)で、唯一デモに劣る点として
記録された改善候補への対応。

### Changed

- Mermaid出力で、追加/削除されたリレーションの線に矢印ラベル記法
  (`ClassA <|-- ClassB : label`)で`new`/`removed`ラベルを付けるようにした。
  以前は削除されたリレーションをソースコード上のコメント(`%% removed`)で
  示していたが、これはMermaidレンダラーが描画する図には表示されない
  (ソースを直接読まない限り気付けない)ため、実際に図の中に見えるラベルに
  変更した

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
