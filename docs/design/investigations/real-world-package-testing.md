# 実戦テスト: 実在の外部Pythonパッケージに対するdesign-diffの動作検証

**目的**: これまでの検証は自分自身(design-diff)とサンプルコードだけだった。公開後に
他人のコードで何が起きるかを、リリース前に手を動かして確認する。見るべきは
「正しい差分か」ではなく**「壊れずに完走するか」**(クラッシュ・無限ループ・
異常に長い実行時間・空の出力・巨大すぎる図)。

**方法**: pipでインストールできる実在のPythonパッケージ5つ+型注釈がほとんど無い
古いコードベース1つを対象に、実際にgit cloneし、各パッケージ自身の依存関係と
design-diffを同じ venv にインストールした上で(`design-diff`はpy2puml経由で対象
コードを実際にimportするため、対象パッケージの依存が無いと即ImportErrorになる。
実際のユーザーは自分のプロジェクトの依存が揃った環境でdesign-diffを使うため、
これが公平な検証方法)、2つのタグ間で`design-diff diff`を実行した。

## 結果一覧

| パッケージ | バージョン範囲 | 完走可否 | 所要時間 | 気づいた点 |
|---|---|---|---|---|
| requests | v2.31.0 → v2.32.3 | ✅ 完走 | 1.12秒 | `HTTPAdapter.max_retries`属性が2行重複表示される**実バグを発見・修正**(型注釈のみの宣言と`__init__`代入の重複。後述) |
| flask | 3.0.0 → 3.0.3 | ❌ 解析失敗(クリーンに失敗) | 1.37秒 | py2pumlが`werkzeug.local.LocalProxy`(Flaskの`current_app`等)の`repr()`評価時に`RuntimeError: Working outside of application context`で例外。**design-diff自体はクラッシュせず、分かりやすいエラーメッセージを出して終了**(後述の修正) |
| click | 8.1.0 → 8.1.7 | ❌ 解析失敗(クリーンに失敗) | 0.79秒 | py2pumlが`typing.Type`という型注釈を解決できず`ValueError`。同じく分かりやすいエラーで終了 |
| rich | v13.6.0 → v13.7.1 | ❌ 解析失敗(クリーンに失敗) | 1.28秒 | py2pumlが文字列リテラルの前方参照`Optional["Live"]`を解決できず`ValueError`。同じく分かりやすいエラーで終了 |
| httpx | 0.26.0 → 0.27.0 | ❌ 解析失敗(クリーンに失敗) | 1.00秒 | py2pumlが`typing.Dict`という型注釈を解決できず`ValueError`(clickと同種) |
| requests(旧) | v0.10.0 → v0.13.0(2012年頃、Python 2時代) | ❌ 解析失敗(クリーンに失敗) | 0.75秒 | Python 3では`cookielib`(Python 2専用モジュール)が無くimport自体が失敗。design-diffの対応範囲外(Python 3で実行できないコードは解析できない)だが、これもクラッシュではなく分かりやすいエラーで終了 |

## 総括

- **クラッシュ・無限ループ・異常に長い実行時間・巨大すぎる図は1件も発生しなかった**。
  全ケースが1.4秒以内に、クラッシュではなく制御されたエラーメッセージ(または
  正常な出力)で終了した。これがこの調査の最重要の結論
- **一方で、6件中2件しか完走しなかった**(requestsの新しい版と、実質的に同じ
  コードベースの古い版はカウント方法により成功/失敗が変わるため、厳密には
  「型注釈が豊富な現代的なパッケージ4/4が解析失敗」という結果。この点は
  README/CHANGELOGに正直に記載する必要がある(下記)
- 失敗の根本原因はいずれも**py2puml本体**の型注釈解決ロジックの制約であり、
  design-diff固有のバグではない。3つの異なるパターンを実際に発見した:
  1. モジュールレベルで実行時コンテキスト依存のオブジェクト(Flaskの`current_app`等、
     `werkzeug.local.LocalProxy`)にアクセスするコードがあると、`repr()`評価が
     失敗して解析全体が落ちる
  2. `typing.Type`/`typing.Dict`のように、`typing`モジュールを`import typing`で
     読み込み`typing.X`の形で参照する型注釈を、py2pumlの名前解決ロジックが
     解決できない(`from typing import X`の形なら問題ない可能性がある。未検証)
  3. `Optional["ClassName"]`のような、文字列リテラルによる前方参照(循環import
     回避のための一般的なイディオム)をpy2pumlが無効な型注釈と誤判定する
- design-diffはpy2pumlをforkしない方針([docs/design/architecture.md](../architecture.md)
  §7で既に決定済み)のため、これらの根本原因そのものを直接修正することはできない

## 修正した問題

1. **属性の重複表示バグ(修正済み)**: クラス本体で型だけ宣言し(`x: SomeType`。
   値の代入は無い)、`__init__`内で`self.x = ...`と代入する、よくあるPythonの
   イディオムに対し、py2pumlは同名の属性を「static=True(クラス本体の注釈)」と
   「static=False(インスタンス属性)」の2つの別属性として重複して返す。
   `requests.adapters.HTTPAdapter.max_retries`で実際に発生することを確認し、
   `_dedupe_attributes()`で1つにまとめるよう修正した
2. **解析失敗時の不親切なエラー(修正済み)**: 上記3パターンのいずれも、以前は
   py2pumlの生の巨大なPythonトレースバックがそのままCLI/Actionの標準エラー出力に
   出ていた(クラッシュではないが、原因が分かりにくい)。`Py2pumlExtractionError`を
   CLI/Action双方でキャッチし、既知の3パターンを説明した上で非ゼロ終了するように
   修正した

## 修正しなかった問題(README Limitationsに記載)

py2puml本体の型注釈解決ロジックの制約(上記3パターン)そのものは、py2pumlを
forkしない方針のため直接修正しない。型注釈が豊富な現代的なパッケージほど
この制約に触れやすいという逆説的な結果になっており、これは正直にREADMEの
Limitationsに明記する。
