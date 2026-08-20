# Python以外の言語への拡張余地の評価(調査のみ、実装はしない)

**依頼**: ドメイン層とapplication層は言語非依存に作ってあるはずだが、抽出
アダプタを差し替えれば済むのか、それとも中間表現(IR)に手を入れる必要が
あるのかを設計面から評価する。TypeScriptを主な検討対象とする。

## 結論(先に)

**抽出アダプタ(ExtractorPort実装)を新規に書くだけで済み、中間表現(IR)・
ドメイン層のdiffアルゴリズム・Mermaid/JSONレンダラーは変更不要**、という
評価になった。実際に`grep`で確認した限り、domain層・application層の
コード(型シグネチャ)にPython固有の型は一切現れない。ただし、下記2点の
**Python固有の「命名・規約」の漏れ**が見つかった。これはIRのデータ構造
そのものの変更を要求するものではないが、新しい言語のアダプタを書く際に
守るべき制約として認識しておく必要がある。

## 1. 実際に確認した「言語非依存性」の裏付け

```
$ grep -rn "Python\|python" src/design_diff/domain/*.py src/design_diff/application/*.py src/design_diff/application/use_cases/*.py
src/design_diff/application/ports.py:31:    """1スナップショット分のPythonパッケージからSnapshotIRを抽出する。
```

ヒットは`ExtractorPort`の**docstring**(コメント)1件のみで、型シグネチャや
ロジックには一切Python固有の型・処理が現れない。`ExtractorPort.extract(self,
path: Path, package: str, ...)`のシグネチャ自体は、`package`という**変数名**
こそPython的だが、型は単なる`str`であり、TypeScript向けアダプタが
「解析対象のルートディレクトリ」「tsconfig.jsonのパス」等、別の意味で
この引数を解釈しても構造的には何の問題もない(Protocolの形さえ満たせばよい。
architecture.md §2.2で既に実測確認済みの設計)。

`domain/model.py`のIR(`ClassIR`/`AttributeIR`/`MethodIR`/`ParameterIR`/
`RelationIR`/`RelationType`)は、`fqn: str`(完全修飾名。ただの文字列)、
`is_abstract: bool`、`static: bool`のように、Python・TypeScript・Java等
多くのクラスベースOOP言語に共通する概念のみで構成されている。
`RelationType.COMPOSITION`/`INHERITANCE`も同様に言語非依存な概念。

## 2. 見つかった2つの「Python固有の漏れ」(いずれもIR変更不要)

### 漏れ1: `include_dunder`というapplication層の引数名

`ComputeDesignDiffUseCase.execute(self, base_ref, head_ref, package, *,
include_dunder: bool = False)`
(`src/design_diff/application/use_cases/compute_design_diff.py:38-39`)。

「dunder」(`__init__`のような前後2重アンダースコアのメソッド)はPython
特有の命名規約であり、TypeScript(コンストラクタは`constructor`、演算子
オーバーロードの概念自体が無い等)にはそのまま対応するものが無い。ただし
実際にdunderかどうかを判定するロジック自体は`_worker.py`の
`_DUNDER_RE = re.compile(r"^__.+__$")`という**アダプタ内**に閉じ込められて
おり、application層はこの`bool`値をそのまま素通しするだけで解釈しない。
つまり**機能的な結合はしていない**が、**引数名という「語彙」がPython色を
帯びている**。TypeScriptのアダプタを書く場合、この引数は「TSアダプタに
とっての `__init__` 的なもの」が無いため常に無視する(あるいは将来的に
`include_boilerplate`のような、より汎用的な名前にリネームする)ことになる。
実害はないが、複数言語対応を本格的に進める場合はリネームを検討する価値がある。

### 漏れ2: MermaidRendererがfqnをドット区切りだと仮定している

`src/design_diff/adapters/rendering/mermaid_renderer.py:96-103`:

```python
def _short_label(fqn: str) -> str:
    return fqn.rsplit(".", 1)[-1]


def _namespace(fqn: str) -> str | None:
    if "." not in fqn:
        return None
    return fqn.rsplit(".", 1)[0]
```

`namespace`によるグループ化・短縮ラベルの生成が、fqnが**ドット区切り**で
あることを前提にしている。これはdomain層(`ClassIR.fqn`はただの`str`、
区切り文字を規定していない)の制約ではなく、**レンダリングアダプタの実装
詳細**。TypeScriptのファイルパス(`src/models/Car.ts`のようにスラッシュ
区切りが自然)をそのままfqnにすると、この関数は正しく分割できない。

対応は単純: 新しい言語のExtractorアダプタが、**自身のfqnをドット区切りに
正規化して返す**(例: `src/models/Car.ts`の`Car`クラスを`src.models.Car`
という形にする)だけでよい。IR自体(`fqn: str`)にもMermaidRendererにも
変更は不要で、**「fqnはドット区切りで返すこと」というExtractorPort実装者
向けの暗黙の規約**として、`ExtractorPort`のdocstringに明記しておくのが
望ましい(現状は書かれていない。将来複数言語対応に着手する際のTODO)。

## 3. 新しい言語のExtractorアダプタに求められるもの

`ExtractorPort.extract(path: Path, package: str, *, include_dunder: bool =
False) -> SnapshotIR`を満たす実装を1つ書けばよい。参考実装
(`Py2pumlExtractor`+`_worker.py`)がやっていることを言語非依存に言い換えると:

1. 指定パス配下のソースを解析し、対象「パッケージ/モジュール境界」内で
   定義されたクラス(に相当する概念: TSなら`class`、`interface`も検討対象)を
   列挙する
2. 各クラスの属性(フィールド)・メソッドと、それぞれの型を解決する
3. 型からクラス間の依存関係(コンポジション・継承)を導出する
4. `SnapshotIR`(`{fqn: ClassIR}`の辞書 + `RelationIR`の集合)に詰めて返す

### TypeScriptの場合: `typescript`パッケージ(TS Compiler API)が現実的な選択肢

Pythonの場合、design-diffは「実際に対象コードをimportして実行時に型を
解決する」(`typing.get_type_hints()`)という戦略を取らざるを得なかった
(Pythonには実行せずに型を確定させる標準の手段が無いため)。これが今回の
実戦テストで散々苦労した根本原因(importのエイリアス・TYPE_CHECKING限定
importでの型解決の失敗、対象パッケージ自身の依存関係が必要、対象コードを
実行することのセキュリティ上の注意点)だった。

**TypeScriptはこの点で本質的に有利**: `typescript`パッケージ(公式コンパイラ)
の`ts.createProgram()`+`TypeChecker`は、**対象コードを一切実行せずに**
静的に型を解決できる。これは:

- **実行に伴うセキュリティリスクが無い**(design-diffの現行READMEの
  「Security」節が抱える「対象コードを実際にimportして解析する」という
  懸念が、TS版アダプタには原理的に発生しない)
- **対象パッケージ自身の依存関係が未インストールでも、型定義(`.d.ts`)さえ
  あれば解決できる可能性が高い**(実戦テストで踏んだ`ModuleNotFoundError`
  系の問題が起きにくい)
- 循環import・型エイリアスのような、今回Python側で苦労した問題群は、TSの
  型チェッカーが本来の実務(IDEの型補完・エラー表示)で日常的に正しく
  解決している領域であり、design-diff独自に解決策を編み出す必要が薄い

一方で、TS Compiler APIを使った新規アダプタの実装自体は、`_worker.py`
(Pythonの`typing.get_type_hints()`ベースの自前実装、約400行)と同等以上の
実装コストがかかる、独立した新規開発である。**IRやドメイン層への変更が
不要**という結論は変わらないが、「アダプタを差し替えるだけ」を「小さい
作業」だと誤解しないよう明記しておく。

## 4. 結論

| 問い | 答え |
|---|---|
| ドメイン層(IR・diffアルゴリズム)に手を入れる必要はあるか | **無い**。`fqn: str`等、既存の型はそのまま言語非依存に使える |
| application層に手を入れる必要はあるか | **無い**(`include_dunder`という引数名の語彙がPython寄りだが、機能的な変更は不要) |
| レンダリングアダプタ(Mermaid/JSON)に手を入れる必要はあるか | **無い**。ただし新言語のExtractorが**ドット区切りのfqn**を返すことが前提条件 |
| 抽出アダプタ(ExtractorPort実装)は新規に書く必要があるか | **必要**。言語ごとの型解決・クラス発見のロジックが本体であり、これ自体は軽くない実装量になる |
| TypeScriptの場合、Pythonより楽になる部分はあるか | **ある**。TS Compiler APIによる静的型解決は対象コードを実行せずに済み、今回Python側で苦労した問題群(エイリアス・TYPE_CHECKING・依存関係インストール漏れ)が構造的に起きにくい |

## 5. 調査時点のステータス

調査のみ実施。設計方針の変更・実装着手はしていない。将来TypeScript(または
他言語)対応に着手する場合は、`docs/design/`に正式な設計ドキュメント
(`ExtractorPort`実装の詳細設計、fqn規約の明文化、`include_dunder`の
リネーム要否)を書き、レビューを経ること(CLAUDE.md「設計ファースト」方針)。
