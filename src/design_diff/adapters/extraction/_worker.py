"""py2pumlサブプロセスワーカー。architecture.md §5.3, §5.4。

1回の起動で1スナップショットだけを抽出する。base/headをまたいで同一プロセス内で
呼び出してはならない(sys.modulesキャッシュ衝突。§5.3の実測)。
Py2pumlExtractor がこのモジュールをサブプロセスとして起動し、プロセス分離を隠蔽する。

使い方:
    python _worker.py <root_path> <package> [--include-dunder]

(注意: `-m design_diff.adapters.extraction._worker`ではなく.pyのファイルパスで
直接起動すること。`-m`起動は`design_diff`パッケージを先にimportしてしまい、
解析対象がたまたま`design_diff`という名前だと自分自身と衝突する。Py2pumlExtractor
参照)

標準出力にJSON({"package": ..., "classes": {...}, "relations": [...]})を1行で出力する。

## 属性の型解決・依存関係抽出は自前実装(HQ指摘・実戦テストの回帰対応)

実在の外部パッケージ(click/httpx/rich/flask)に対する実戦テストで、py2puml本体の
型注釈解決ロジック(`py2puml.parsing.moduleresolver`/`compoundtypesplitter`)が、
以下のようなよくあるPythonのイディオムで解析全体を失敗させることが判明した:

- `import typing as t`のような**importのエイリアス**(click)
- 循環import回避のための**`TYPE_CHECKING`限定import**(`Optional["Live"]`のような
  文字列前方参照。rich)

真因は、py2pumlが型注釈を「モジュールの実行時の名前空間から`getattr()`で引く」
方式で解決しており、標準ライブラリの`typing.get_type_hints()`のような正式な
(エイリアス・前方参照・遅延評価に対応した)解決手段を使っていないことにある。
司令塔の実機検証で、`get_type_hints()`ならこれらのケースを正しく解決できることが
証明された(詳細: docs/design/investigations/py2puml-resolution-failures-root-cause.md)。

そのため、**クラスの発見(どのクラスが対象パッケージに属するか)は引き続き
py2pumlの`filter_domain_definitions`を使うが、属性の型解決とそこから導かれる
依存関係の抽出は自前で行う**(`own_attributes`/`_composition_targets`)。
py2pumlの`Inspector.inspect()`はパッケージ全体を同期的に処理してから最後に
まとめて結果を返す設計(1クラスごとのストリーミングではない)ため、この
crashしうる部分(`inspect_static_attributes`/`parse_class_constructor`)を
経由する限り、1クラスの失敗がパッケージ全体の解析を道連れにしてしまう。
自前実装なら**クラス単位で例外を握りつぶし、そのクラスだけ縮退させて
(型注釈を解決できない場合は文字列のまま表示し)、残りのクラスの解析を
継続できる**。
"""

from __future__ import annotations

import ast
import enum
import importlib
import inspect
import json
import re
import sys
import textwrap
import typing
from pathlib import Path
from pkgutil import walk_packages

from py2puml.inspection.inspectmodule import filter_domain_definitions

# レビューフィードバック(表示品質)優先度1: ダンダーメソッドは既定で除外する。
# dataclassが自動生成する __init__/__eq__/__repr__/__hash__ や、typing.Protocolが
# 自動生成する __subclasshook__ が全クラスに並び図がノイズだらけになる上、
# フィールドを1つ足すたびに __init__ が「変更されたメソッド」として報告され、
# 属性差分(AttributeDiff)と二重計上される。--include-dunder相当のopt-inは残す。
_DUNDER_RE = re.compile(r"^__.+__$")

# レビューフィードバック優先度2: 型表記の正規化。
# `<class 'float'>` や `typing.List[pkg.models.Product]` という生のreprを
# `float` / `List[Product]` のような読める形に整形する。
_CLASS_REPR_RE = re.compile(r"<(?:class|enum) '([\w.]+)'>")
_DOTTED_NAME_RE = re.compile(r"\b(?:[A-Za-z_][\w]*\.)+([A-Za-z_]\w*)\b")

# 型が解決できず生の注釈文字列のままになった場合、そこから大文字始まりの識別子
# らしき候補を拾い、同一スナップショット内の同名クラスと名前ベースで突き合わせる
# (HQ指摘: 「解決できなかった型注釈は文字列のまま表示し、可能なら同一スナップショット
# 内に同名クラスがあれば依存として結びつける」)。
_CAPITALIZED_NAME_RE = re.compile(r"\b[A-Z][A-Za-z0-9_]*\b")


def format_type(raw: str | None) -> str | None:
    """型の生repr文字列を、モジュール修飾を剥がした読める形に正規化する。

    例:
        "<class 'float'>"                              -> "float"
        "typing.List[shop.models.Product]"              -> "List[Product]"
        "typing.Optional[shop.models.Product]"           -> "Optional[Product]"

    ドッグフーディングで発見した回帰: py2pumlはUmlAttribute.typeとしてNoneを返す
    ケースがある(型が解決できない属性など)。Noneはそのまま素通りさせる。
    """
    if raw is None:
        return None
    text = _CLASS_REPR_RE.sub(lambda m: m.group(1), raw)
    text = text.replace("typing.", "")
    text = _DOTTED_NAME_RE.sub(lambda m: m.group(1), text)
    return text


def own_methods(cls: type, *, include_dunder: bool = False) -> list[dict]:
    """clsが自分で定義したメソッドのみを抽出する(継承分は含まない)。

    指摘1対応: inspect.getmembers(cls, predicate=isfunction)はMRO(継承元)を辿って
    基底クラスのメソッドまで返してしまうため使わない。vars(cls)(=cls.__dict__)を直接見て
    自クラス定義分のみに絞る。副産物としてclassmethodの取りこぼしも解消される
    (architecture.md §5.4で実測比較済み)。

    `include_dunder=False`(既定)ではダンダーメソッド(`__xxx__`)を除外する
    (レビューフィードバック優先度1)。
    """
    methods: list[dict] = []
    for name, obj in vars(cls).items():
        if not include_dunder and _DUNDER_RE.match(name):
            continue

        # self/clsは表示ノイズのため除外する(全メソッドに機械的に付くだけで情報量がない。
        # ドッグフーディングで発見)。staticmethodには元々self/clsが付かないため対象外。
        skip_first_param = 0
        if isinstance(obj, staticmethod):
            fn = obj.__func__
        elif isinstance(obj, classmethod):
            fn = obj.__func__
            skip_first_param = 1  # cls
        elif inspect.isfunction(obj):
            fn = obj
            skip_first_param = 1  # self
        else:
            continue  # プロパティ・クラス変数などは対象外(属性側で別途扱う)

        try:
            signature = inspect.signature(fn)
        except (TypeError, ValueError):
            # C拡張など、シグネチャが取得できないものはスキップする
            continue

        empty_param = inspect.Parameter.empty
        parameters = [
            {
                "name": param.name,
                "type": None if param.annotation is empty_param else format_type(str(param.annotation)),
            }
            for param in list(signature.parameters.values())[skip_first_param:]
        ]
        empty = inspect.Signature.empty
        return_type = (
            None if signature.return_annotation is empty else format_type(str(signature.return_annotation))
        )
        methods.append({"name": name, "parameters": parameters, "return_type": return_type})

    methods.sort(key=lambda m: m["name"])  # diffの安定性のため決定的な順序にする
    return methods


# ---------------------------------------------------------------------------
# 属性の型解決(自前実装。HQ指摘・実戦テストの回帰対応)
# ---------------------------------------------------------------------------


def own_annotations(cls: type) -> dict[str, object]:
    """自クラス自身が定義したクラスレベルの型注釈(基底クラス由来を除く)。

    own_methodsと同じ方針でvars(cls)(=cls.__dict__)を直接見る(MROを辿らない)。
    """
    return dict(vars(cls).get("__annotations__", {}))


def resolve_type_hints(obj: object) -> dict[str, object] | None:
    """typing.get_type_hints()で実際に解決された型オブジェクトを返す。

    py2pumlのAST/getattrベースの解決と違い、実行時にモジュールのglobalsに対して
    注釈を評価するため、importのエイリアス(`import typing as t`)や循環import回避の
    ための`TYPE_CHECKING`限定importが絡む前方参照も正しく解決できる。解決できない
    場合はNoneを返す(呼び出し側でクラス単位のフォールバックに委ねる。HQ指摘:
    「get_type_hints が例外を投げたクラス・属性は、そのクラスだけを縮退させること」)。
    """
    try:
        return typing.get_type_hints(obj)
    except Exception:  # noqa: BLE001 - 対象コード側のあらゆる理由での解決失敗に備える
        return None


def _iter_type_leaf_classes(annotation: object) -> typing.Iterator[type]:
    """`Dict[str, Engine]`や`Optional[Battery]`のような複合型注釈から、含まれる
    クラスオブジェクトを再帰的に取り出す(コンポジション依存の検出用)。
    """
    if annotation is None:
        return
    origin = typing.get_origin(annotation)
    if origin is not None:
        for arg in typing.get_args(annotation):
            yield from _iter_type_leaf_classes(arg)
    elif inspect.isclass(annotation):
        yield annotation


def _self_attribute_annotations(cls: type) -> dict[str, ast.expr]:
    """自クラスの`__init__`内、`self.attr: Type = value`という代入(型注釈付き)から、
    属性名と型注釈のASTノードの対応を得る。

    このパターンの型注釈はfunctionの`__annotations__`にもクラスの`__annotations__`
    にも保存されない(PEP 526: 複合ターゲットへの注釈は評価はされるが保存されない)
    ため、AST解析でしか取得できない。
    """
    init = vars(cls).get("__init__")
    if init is None or not inspect.isfunction(init):
        return {}
    try:
        source = textwrap.dedent(inspect.getsource(init))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        return {}

    result: dict[str, ast.expr] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Attribute)
            and isinstance(node.target.value, ast.Name)
            and node.target.value.id == "self"
        ):
            result.setdefault(node.target.attr, node.annotation)
    return result


def _self_attribute_assignments(cls: type) -> dict[str, str | None]:
    """自クラスの`__init__`内、`self.attr = <式>`という単純代入(型注釈なし)から、
    属性名を洗い出す。

    右辺がパラメータそのもの(`self.attr = param_name`)の場合はパラメータ名を
    返し、型はパラメータ自身の注釈(`__init__`のシグネチャ)から借りる
    (rich.console.Console.live等、実際のパッケージで確認したイディオム)。
    右辺が関数呼び出しやリテラルなど単純な名前参照でない場合(例:
    `self.max_retries = Retry.from_int(max_retries)`、`self.config = {}`。
    requests.adapters.HTTPAdapterで実際に確認)は、型不明(None)の属性として
    記録する。これはpy2puml本体のparse_class_constructorと同じ、素朴な
    「型が取れない属性も出す」挙動を踏襲するため(型が取れないだけで属性の
    存在自体は無視しない)。
    """
    init = vars(cls).get("__init__")
    if init is None or not inspect.isfunction(init):
        return {}
    try:
        source = textwrap.dedent(inspect.getsource(init))
        tree = ast.parse(source)
    except (OSError, TypeError, SyntaxError):
        return {}

    result: dict[str, str | None] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Attribute)
            and isinstance(node.targets[0].value, ast.Name)
            and node.targets[0].value.id == "self"
        ):
            param_name = node.value.id if isinstance(node.value, ast.Name) else None
            result.setdefault(node.targets[0].attr, param_name)
    return result


def _eval_annotation_node(node: ast.expr, globalns: dict) -> object | None:
    """`self.attr: Type = value`のTypeノードを、`__init__`が定義されたモジュールの
    globalsに対して評価し、実際の型オブジェクトを得る。design-diffは対象コードを
    既にimportして実行しているため(README「制約・セキュリティ」参照)、その一部
    (型注釈の式)を評価すること自体は新しいリスクを追加しない。
    """
    try:
        code = compile(ast.Expression(body=node), "<design-diff-annotation>", "eval")
        return eval(code, globalns)  # noqa: S307 - 既にimport済みの対象コードのglobalsのみ使う
    except Exception:  # noqa: BLE001 - 評価できない注釈は諦めてフォールバックに委ねる
        return None


def own_attributes(cls: type) -> list[dict]:
    """自クラス自身の属性(クラスレベル注釈 + `__init__`での代入)を、
    get_type_hints()ベースで型解決して抽出する。

    型が解決できない属性は、生の注釈をformat_typeで整形した文字列のまま返す
    (このクラスの他の属性・他のクラスの解析は継続する。HQ指摘の「そのクラス
    だけ縮退させる」を属性単位でも実現している)。
    """
    attributes: list[dict] = []
    seen_names: set[str] = set()

    is_dataclass_type = _is_dataclass_like(cls)
    own_annotation_names = own_annotations(cls)
    class_hints = resolve_type_hints(cls)  # クラス全体で解決を試みる(1回で済むよう先に)

    for name, raw in own_annotation_names.items():
        seen_names.add(name)
        resolved = class_hints.get(name) if class_hints is not None else None
        if resolved is None:
            resolved = _resolve_single(cls, raw)
        attributes.append(_build_attribute(name, resolved, raw, static=not is_dataclass_type))

    # __init__ 由来のインスタンス属性(クラスレベルで既に注釈済みのものは除く。
    # requests.adapters.HTTPAdapter.max_retriesと同じ、重複計上を避けるため)
    init = vars(cls).get("__init__")
    init_hints = resolve_type_hints(init) if init is not None and inspect.isfunction(init) else None

    for attr_name, node in _self_attribute_annotations(cls).items():
        if attr_name in seen_names:
            continue
        seen_names.add(attr_name)
        resolved = _eval_annotation_node(node, getattr(init, "__globals__", {}))
        raw = ast.unparse(node) if hasattr(ast, "unparse") else None
        attributes.append(_build_attribute(attr_name, resolved, raw, static=False))

    for attr_name, param_name in _self_attribute_assignments(cls).items():
        if attr_name in seen_names:
            continue
        seen_names.add(attr_name)
        resolved = init_hints.get(param_name) if param_name is not None and init_hints is not None else None
        attributes.append(_build_attribute(attr_name, resolved, None, static=False))

    # 古い形式のnamedtuple(collections.namedtuple。型注釈を持たない)は
    # py2pumlと同様、フィールドをAny型の属性として扱う
    fields = getattr(cls, "_fields", None)
    if fields is not None:
        for field_name in fields:
            if field_name in seen_names:
                continue
            attributes.append({"name": field_name, "type": "Any", "static": False})

    return attributes


def _is_dataclass_like(cls: type) -> bool:
    """dataclassのクラスレベル注釈はpy2puml同様、インスタンス属性(static=False)
    として扱う(dataclassの`x: int`は実体としてはインスタンス属性のため)。
    """
    import dataclasses

    return dataclasses.is_dataclass(cls)


def _resolve_single(cls: type, raw: object) -> object | None:
    """クラス全体のget_type_hints()が失敗した場合に、この属性だけでも個別解決を
    試みる(1つの属性の失敗が他の属性まで巻き込まないようにするベストエフォート)。
    """
    if isinstance(raw, str):
        try:
            return eval(  # noqa: S307 - 既にimport済みの対象コードのモジュールglobalsのみ使う
                raw, dict(vars(sys.modules.get(cls.__module__, object()))), None
            )
        except Exception:  # noqa: BLE001
            return None
    return raw if inspect.isclass(raw) or typing.get_origin(raw) is not None else None


def _build_attribute(name: str, resolved: object | None, raw: object | None, *, static: bool) -> dict:
    if resolved is not None:
        return {"name": name, "type": format_type(_type_repr(resolved)), "static": static}
    if raw is not None:
        return {"name": name, "type": format_type(str(raw).strip("'\"")), "static": static}
    return {"name": name, "type": None, "static": static}


def _type_repr(resolved: object) -> str:
    if inspect.isclass(resolved):
        return f"<class '{resolved.__module__}.{resolved.__qualname__}'>"
    return str(resolved)


def _composition_targets(
    cls: type, attributes_raw_resolved: list[object], root_module_name: str
) -> set[type]:
    targets: set[type] = set()
    for resolved in attributes_raw_resolved:
        for leaf in _iter_type_leaf_classes(resolved):
            if leaf is cls:
                continue
            module_name = getattr(leaf, "__module__", "")
            if module_name == root_module_name or module_name.startswith(f"{root_module_name}."):
                targets.add(leaf)
    return targets


def _unresolved_type_names(attributes: list[dict], resolved_names: set[str]) -> dict[str, str]:
    """型が文字列のまま(未解決)残った属性から、名前ベース突き合わせの対象となる
    候補(大文字始まりの識別子)を拾う。HQ指摘: 「解決できなかった型注釈は文字列の
    まま表示し、可能なら同一スナップショット内に同名クラスがあれば依存として
    結びつける」への対応。
    """
    candidates: dict[str, str] = {}
    for attribute in attributes:
        if attribute["name"] in resolved_names or attribute["type"] is None:
            continue
        for match in _CAPITALIZED_NAME_RE.finditer(attribute["type"]):
            candidates[attribute["name"]] = match.group(0)
    return candidates


# ---------------------------------------------------------------------------
# クラスの発見(py2puml由来。ここはpy2pumlの安全な部分のみを使う)
# ---------------------------------------------------------------------------


def _iter_target_classes(package_path: Path, package: str) -> typing.Iterator[type]:
    """py2pumlのInspectorと同じ手法(pkgutil.walk_packages +
    py2puml.inspection.inspectmodule.filter_domain_definitions)で、対象パッケージに
    属するクラスを列挙する。属性/関係の抽出(クラッシュしうる部分)はここでは行わない。
    """
    seen_fqns: set[str] = set()

    def _yield_new(module) -> typing.Iterator[type]:
        for cls in filter_domain_definitions(module, package):
            fqn = f"{cls.__module__}.{cls.__qualname__}"
            if fqn in seen_fqns:
                continue
            seen_fqns.add(fqn)
            if issubclass(cls, enum.Enum):
                continue  # Enumは対象外(architecture.md §3.5)
            yield cls

    if package_path.is_dir():
        yield from _yield_new(importlib.import_module(package))
        prefix = f"{package}." if package else ""
        for _, module_name, _ in walk_packages([str(package_path)], prefix):
            if module_name.rsplit(".", 1)[-1] == "__main__":
                # 実戦テストで発見した回帰(flask): `__main__.py`は`python -m <pkg>`
                # でのみ実行される前提で書かれているため、ガード無しでモジュール
                # トップレベルの処理(CLIの起動等)を書いているパッケージがある
                # (flask/__main__.pyは`from .cli import main; main()`のみで、
                # `if __name__ == "__main__":`によるガードが無い)。design-diffが
                # importするとCLIが実際に起動し、design-diff自身のsys.argvを
                # パースしようとして失敗する。他の静的解析ツールでも一般的に
                # 避けられている慣習に倣い、`__main__`モジュールは解析対象から除く。
                continue
            try:
                module = importlib.import_module(module_name)
            except Exception:  # noqa: BLE001 - 1モジュールのimport失敗で全体を止めない
                continue
            yield from _yield_new(module)
    else:
        yield from _yield_new(importlib.import_module(package))


def extract_snapshot(root: Path, package: str, *, include_dunder: bool = False) -> dict:
    # 罠1対策: symlink未解決だと対象クラスが無言で消える(architecture.md §5.2)。
    resolved_root = root.resolve()
    package_parts = package.split(".")

    # ドッグフーディングで発見した回帰(design-diff自身がsrc-layout):
    # `root / package` にパッケージが存在しない場合、`root / "src" / package` も試す。
    candidate = resolved_root.joinpath(*package_parts)
    src_candidate = resolved_root.joinpath("src", *package_parts)
    has_src_folder = (resolved_root / "src").exists()
    if not candidate.is_dir() and src_candidate.is_dir():
        candidate = src_candidate
    package_path = candidate

    # py2pumlのInspectorと同じsys.path設定(Inspector.inspect()と同等の効果を、
    # 自前の_iter_target_classesでも必要とするため明示的に行う)。
    if has_src_folder:
        sys.path.insert(0, str(resolved_root / "src"))
    sys.path.insert(0, str(resolved_root))

    class_objects_by_fqn: dict[str, type] = {}
    for cls in _iter_target_classes(package_path, package):
        fqn = f"{cls.__module__}.{cls.__qualname__}"
        class_objects_by_fqn[fqn] = cls

    classes: dict[str, dict] = {}
    relations: list[dict] = []
    seen_relations: set[tuple[str, str, str]] = set()

    def _add_relation(source_fqn: str, target_fqn: str, rel_type: str) -> None:
        key = (source_fqn, target_fqn, rel_type)
        if key in seen_relations:
            return
        seen_relations.add(key)
        relations.append({"source_fqn": source_fqn, "target_fqn": target_fqn, "type": rel_type})

    for fqn, cls in class_objects_by_fqn.items():
        try:
            attributes = own_attributes(cls)
        except Exception:  # noqa: BLE001 - 1クラスの失敗で全体を落とさない(HQ指摘)
            attributes = []
        try:
            methods = own_methods(cls, include_dunder=include_dunder)
        except Exception:  # noqa: BLE001
            methods = []

        classes[fqn] = {
            "fqn": fqn,
            "name": cls.__name__,
            "is_abstract": inspect.isabstract(cls),
            "attributes": attributes,
            "methods": methods,
        }

        for base in getattr(cls, "__bases__", ()):
            base_fqn = f"{base.__module__}.{base.__qualname__}"
            if base_fqn in class_objects_by_fqn:
                _add_relation(base_fqn, fqn, "inheritance")

    # コンポジション依存(解決できた型から)+ 名前ベースの補完(解決できなかった型)
    by_short_name: dict[str, list[str]] = {}
    for target_fqn, class_payload in classes.items():
        by_short_name.setdefault(class_payload["name"], []).append(target_fqn)

    for fqn, cls in class_objects_by_fqn.items():
        try:
            resolved_values = _own_resolved_attribute_values(cls)
        except Exception:  # noqa: BLE001
            resolved_values = []
        for target_cls in _composition_targets(cls, resolved_values, package):
            target_fqn = f"{target_cls.__module__}.{target_cls.__qualname__}"
            if target_fqn in class_objects_by_fqn:
                _add_relation(fqn, target_fqn, "composition")

        unresolved = _unresolved_type_names(classes[fqn]["attributes"], resolved_names=set())
        for candidate_name in unresolved.values():
            matches = by_short_name.get(candidate_name, [])
            if len(matches) == 1 and matches[0] != fqn:
                _add_relation(fqn, matches[0], "composition")

    return {"package": package, "classes": classes, "relations": relations}


def _own_resolved_attribute_values(cls: type) -> list[object]:
    """own_attributes()と同じ探索を行い、コンポジション検出用に解決済みの型
    オブジェクト(文字列にフォールバックする前の生の値)だけを集める。
    """
    values: list[object] = []
    is_dataclass_type = _is_dataclass_like(cls)
    class_hints = resolve_type_hints(cls)
    for name, raw in own_annotations(cls).items():
        resolved = class_hints.get(name) if class_hints is not None else None
        if resolved is None:
            resolved = _resolve_single(cls, raw)
        if resolved is not None:
            values.append(resolved)
        del is_dataclass_type  # staticかどうかはコンポジション検出に無関係

    init = vars(cls).get("__init__")
    init_hints = resolve_type_hints(init) if init is not None and inspect.isfunction(init) else None

    for _attr_name, node in _self_attribute_annotations(cls).items():
        resolved = _eval_annotation_node(node, getattr(init, "__globals__", {}))
        if resolved is not None:
            values.append(resolved)

    for _attr_name, param_name in _self_attribute_assignments(cls).items():
        resolved = init_hints.get(param_name) if param_name is not None and init_hints is not None else None
        if resolved is not None:
            values.append(resolved)

    return values


def main() -> None:
    args = sys.argv[1:]
    include_dunder = "--include-dunder" in args
    positional = [a for a in args if a != "--include-dunder"]

    if len(positional) != 2:
        usage = (
            "usage: python _worker.py <root_path> <package> [--include-dunder]"
        )
        print(usage, file=sys.stderr)
        sys.exit(2)

    root, package = Path(positional[0]), positional[1]
    payload = extract_snapshot(root, package, include_dunder=include_dunder)
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
