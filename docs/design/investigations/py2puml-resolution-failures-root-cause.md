# py2pumlの型解決が失敗する3パターンの真因(最小再現付き)

**経緯**: [real-world-package-testing.md](./real-world-package-testing.md)で、
flask/click/rich/httpxの解析失敗について「`typing.X`形式の型注釈をpy2pumlが
解決できない」という説明を書いたが、**この説明は不正確だった**。最小再現コードで
`import typing; ...: typing.Dict[str, Engine]`(エイリアス無し)が正常に解析
できることが分かり、誤りが判明した。本ドキュメントは、実際に10〜20行の最小
コードまで絞り込んで検証した、正確な真因の記録である。

## 結論(先に)

3パターンとも根っこは共通で、**py2pumlが型注釈を「実行時にモジュールの
名前空間から`getattr()`で引く」方式で解決しており、`typing.get_type_hints()`
のような正式な(遅延評価・エイリアス・前方参照に対応した)解決手段を使って
いない**ことに起因する。この方式は、注釈で参照されている名前が「そのモジュール
オブジェクトの実際の`__dict__`に、実行時に本当に束縛されている」場合にしか
機能しない。以下の2つの`design-diff`側では安全に回避できない事情により、
現代的な型注釈を多用するコードほどこの前提が崩れやすい:

1. **`TYPE_CHECKING`限定import**(循環import回避の定石。click/httpx/richで確認)
2. **importのエイリアス**(`import typing as t`。clickで確認)

加えてFlaskのケースは、上記と少し違う**別の**バグ(後述)。

## パターン1・2: TYPE_CHECKING限定import / importエイリアス(click, httpx, rich)

### 最小再現(エイリアス。clickで実際に発生したパターン)

```python
import typing as t


class Engine:
    pass


class Car:
    parts: t.Dict[str, Engine]
```

実行結果:
```
ValueError: Could not resolve type typing.Dict in module <module '...'>:
it needs to be imported explicitly.
```

**司令塔の反証(`import typing`をエイリアス無しで書いた場合)は正しく解析できる**
ことを確認済み。真因は「`typing.Dict`という記法そのもの」ではなく、**py2pumlの
名前解決が、モジュールの`__dict__`に文字通り`typing`という名前が束縛されている
ことを前提にしている**点にある。`import typing as t`だと`__dict__`には`t`しか
無く`typing`という名前は存在しないため、py2puml内部の
`ModuleResolver.resolve_full_namespace_type()`(`py2puml/parsing/moduleresolver.py`)
が`getattr(module, "typing", None)`相当のルックアップに失敗し、解決不能と判定する。

click本体では`import typing as t`が使われている(`src/click/core.py`)。

### 最小再現(TYPE_CHECKING限定import。richで実際に発生したパターン)

```python
from typing import Optional


class Live:
    pass


class Console:
    def __init__(self, live: Optional["Live"] = None):
        self.live = live
```

実行結果(最初):
```
ValueError: Optional["Live"] seems to be an invalid type annotation
```

この最初のエラーは**別の、より浅い**バグ(後述の「試したが効果が限定的だった
回避策」を参照)。それを迂回しても、以下の**より深い**エラーに行き着く:
```
ValueError: Could not resolve type ....Live in module '...': it needs to be
imported explicitly.
```

rich本体では実際に、`Live`クラスは循環import回避のため`TYPE_CHECKING`ブロックの
中でのみimportされ(`rich/console.py`)、`Console.__init__`内で
`live: "Live"`という文字列前方参照として使われている。これは**Pythonの
ローカル変数注釈(関数・メソッドの中の`x: T = value`)は実行時に評価・保存
されない**という言語仕様を利用した、意図的で正当なイディオムである
(`Live`を実際にimportしなくてもコードは正しく動く)。しかしpy2pumlは
コンストラクタのASTを自前で静的解析して注釈のテキストを読み取り、その名前を
**実行時のモジュールオブジェクトに対して**解決しようとするため、
`TYPE_CHECKING`限定でimportされた名前は実行時に存在せず、解決に失敗する。

httpxの`typing.Dict`失敗も同じ「実行時に名前が束縛されていない」系統の問題
(詳細な特定コードパスは未確認だが、上記2パターンのいずれかと同種と推定される)。

### 試したが効果が限定的だった回避策

py2pumlの`remove_forward_references()`(`py2puml/parsing/compoundtypesplitter.py`)
は、`ForwardRef('X')`という特定の repr 形式(解決済みの`typing.ForwardRef`
オブジェクトを`str()`した形)しか前方参照として認識せず、ソースコードに直接
書かれた文字列リテラル`"X"`はそのまま残ってしまい、`Optional["Live"]`のように
引用符付きの文字列が混じった注釈は「無効な型注釈」として弾かれる
(`CompoundTypeSplitter`の`IS_COMPOUND_TYPE`正規表現が引用符を許可していないため)。

この関数はpy2pumlのモジュールレベル関数(クロージャではない)であるため、
文字列リテラルの引用符も剥がすよう拡張する монキーパッチを実際に書いて検証した:

```python
import re
import py2puml.parsing.compoundtypesplitter as cts

_original = cts.remove_forward_references
_QUOTED_RE = re.compile(r'["\']([A-Za-z_][\w.]*)["\']')

def patched(compound_type_annotation, module_name):
    result = _original(compound_type_annotation, module_name)
    if result is None:
        return None
    return _QUOTED_RE.sub(lambda m: f'{module_name}.{m.group(1)}', result)

cts.remove_forward_references = patched
```

最小再現(同一モジュール内、TYPE_CHECKING無し)には効いたが、**rich本体の実際の
ケース(`Live`がTYPE_CHECKING限定import)には効かなかった**。引用符を剥がして
「無効な型注釈」エラーは解消しても、その先で結局「`Live`という名前が実行時の
モジュールに存在しない」という、パターン1と同じ壁にぶつかるため。
つまりこの回避策は**「無効な型注釈」エラーの発生パターンの一部だけを狭く
救うが、実戦テストで実際に遭遇した失敗そのものは直さない**。モンキーパッチを
1つ増やす保守コストに見合わないと判断し、**採用しなかった**。

### design-diffで安全に回避できない理由

- py2pumlの`Inspector.inspect()`は1クラスごとに結果をyieldするストリーミング
  設計ではなく、パッケージ全体を同期的に処理してから最後にまとめてyieldする
  (`py2puml/inspector.py`の`_inspect_package`/`_inspect_module`を確認)。
  そのため「1クラスだけ解析に失敗しても、残りのクラスは返す」という
  部分的な耐障害性を、呼び出し側(design-diff)から安全に後付けすることはできない
- 根本的な解決には、py2pumlの型解決ロジック全体を`typing.get_type_hints()`
  ベースに書き換える(エイリアス・前方参照・遅延評価に正式対応させる)必要が
  あるが、これは実質的にpy2pumlの型解決部分をフォークすることに等しく、
  `docs/design/architecture.md` §7で既に決定した「py2pumlをforkしない」方針に
  反する

## パターン3: 実行時コンテキスト依存オブジェクトへのアクセス(Flask)

こちらは上記2パターンとは**別のバグ**。`resolve_full_namespace_type()`は、
目的の型を見つけるために**モジュールの`vars()`を総当たりで走査し、見つかった
値ごとに`f'{value}'`で文字列化して比較する**(該当コード:
`py2puml/parsing/moduleresolver.py`の`string_repr`関数、
`resolve_full_namespace_type`のローカル関数として定義されている)。

Flaskの`current_app`/`g`/`request`のような`werkzeug.local.LocalProxy`
オブジェクトがモジュールレベルに存在すると、**解決したい型が何であれ**、
この総当たり走査の途中で`LocalProxy`を`str()`しようとして
`RuntimeError: Working outside of application context`が飛ぶ。つまり
**解決対象の型注釈とは無関係に、モジュール内にこの種のオブジェクトが1つでも
あれば解析全体が落ちる**。

### 回避を試みなかった理由

`string_repr`はモジュールレベル関数ではなく`resolve_full_namespace_type`
メソッド内のローカル関数(クロージャ)であるため、パターン1・2のような
「関数を1つ差し替える」形の狭いパッチが効かない。安全に直すには
`resolve_full_namespace_type`メソッド全体(約30行)を丸ごと再実装して
差し替える必要があり、これは事実上py2pumlの当該メソッドをフォークして
保守することに等しい。py2pumlの将来のバージョンでこのメソッドの実装が
変われば、差し替えたコードが気づかないうちに乖離する risk があるため、
**採用しなかった**。

design-diffが対象コードを実際にimportして解析する設計である以上、この種の
「モジュールレベルで実行時コンテキストに依存するオブジェクト」を持つコードは
本質的に解析できない可能性が高い(静的解析だけで完結するツールであれば
この問題は起きない)。

## まとめ

| パターン | 対象 | 真因 | design-diff側の回避 |
|---|---|---|---|
| importエイリアス | click | `import typing as t`のように、注釈が参照する名前がモジュールの`__dict__`に文字通り束縛されていない | 不可(py2pumlの解決ロジックをget_type_hints()ベースに書き換える必要があり、事実上フォークに等しい) |
| TYPE_CHECKING限定import | rich(httpxも同系統と推定) | 循環import回避のため実行時にはimportされない名前を、py2pumlが実行時のモジュール名前空間に対して解決しようとする | 不可(同上)。文字列リテラル前方参照の引用符を剥がすパッチは試したが、この根本問題には効かなかった |
| 実行時コンテキスト依存オブジェクト | flask | 型解決のための`vars(module)`総当たり走査が、対象と無関係なオブジェクトの`str()`失敗で全体クラッシュする | 不可(該当ロジックがクロージャで、狭いパッチが書けない) |

3パターンとも、design-diff固有のバグではなくpy2puml本体の型解決アーキテクチャに
起因し、forkしない方針の範囲では安全に修正できないという結論に至った。
