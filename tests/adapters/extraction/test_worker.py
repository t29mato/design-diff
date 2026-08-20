"""ワーカー内部ロジック(own_methods等)の単体テスト。サブプロセスを介さず高速に検証する。

指摘1の回帰テスト(architecture.md §5.4)を含む:
1. 継承したメソッドを拾わないこと
2. staticmethod/classmethodを取りこぼさないこと

さらにレビューフィードバック(表示品質)の回帰テスト:
3. ダンダーメソッド(__init__/__eq__/__repr__/__hash__/__subclasshook__等)は既定で除外
   (dataclass自動生成やProtocolのノイズ、および属性差分との二重計上を防ぐ)。
   include_dunder=True で明示的に含められる(--include-dunder相当)。
4. 型表記の正規化: `<class 'float'>` は `float` に、`typing.List[pkg.models.Product]` は
   `List[Product]` に、モジュール修飾を剥がして読める形にする。
"""

import typing
import typing as t  # わざとエイリアスで(clickで実際に発生したパターンの再現)
from dataclasses import dataclass

from design_diff.adapters.extraction._worker import format_type, own_attributes, own_methods


class Vehicle:
    def __init__(self, name: str):
        self.name = name

    def drive(self):
        pass


class Car(Vehicle):
    def honk(self, times: int) -> None:
        pass

    @staticmethod
    def static_helper() -> str:
        return "help"

    @classmethod
    def from_name(cls, name: str) -> "Car":
        return cls(name)


class Product:
    pass


class PriceSetter:
    def set_price(self, price: float) -> bool:
        return True


class ProductLister:
    # typing.List/typing.Optionalは、str(annotation)が生成する古いreprを
    # 意図的に再現するために使っている(list[]/X|Noneに直すとテストの意味が消える)。
    def add_products(self, products: typing.List[Product]) -> None:  # noqa: UP006
        pass

    def find(self) -> typing.Optional[Product]:  # noqa: UP045
        return None


class TestOwnMethods:
    def test_excludes_inherited_methods(self):
        methods = own_methods(Car)
        names = {m["name"] for m in methods}
        assert "drive" not in names, "継承元Vehicleのdriveを拾ってはいけない(指摘1)"

    def test_includes_own_instance_method_with_signature(self):
        methods = own_methods(Car)
        honk = next(m for m in methods if m["name"] == "honk")
        param_names = [p["name"] for p in honk["parameters"]]
        assert param_names == ["times"]  # self は表示ノイズのため除外(下記テスト参照)
        assert honk["return_type"] == "None"

    def test_includes_staticmethod(self):
        methods = own_methods(Car)
        names = {m["name"] for m in methods}
        assert "static_helper" in names

    def test_includes_classmethod(self):
        """当初案(inspect.getmembers+isfunction)ではclassmethodが取りこぼされることを実測済み(§5.4)。"""
        methods = own_methods(Car)
        names = {m["name"] for m in methods}
        assert "from_name" in names

    def test_methods_are_sorted_for_deterministic_output(self):
        methods = own_methods(Car)
        names = [m["name"] for m in methods]
        assert names == sorted(names)


class TestOwnMethodsDunderExclusion:
    """レビューフィードバック優先度1: ダンダーメソッドの除外。"""

    def test_excludes_dunder_methods_by_default(self):
        methods = own_methods(Vehicle)
        names = {m["name"] for m in methods}
        assert names == {"drive"}
        assert "__init__" not in names

    def test_includes_dunder_methods_when_opted_in(self):
        methods = own_methods(Vehicle, include_dunder=True)
        names = {m["name"] for m in methods}
        assert "__init__" in names
        assert "drive" in names

    def test_excludes_protocol_boilerplate_by_default(self):
        """typing.Protocolのサブクラスhookが全クラスに並ぶノイズを防ぐ。"""

        class SomePort(typing.Protocol):
            def do_something(self) -> None: ...

        methods = own_methods(SomePort)
        names = {m["name"] for m in methods}
        assert names == {"do_something"}
        assert "__subclasshook__" not in names
        assert "__init__" not in names


class TestOwnMethodsSelfClsStripping:
    """ドッグフーディングで発見した表示ノイズ: 全メソッドに`self`が並び冗長。

    self/clsは全インスタンス/クラスメソッドに機械的に付くだけで情報量がないため、
    UMLの慣習に合わせて表示から除く(JSON側の忠実性より、図の可読性を優先)。
    """

    def test_strips_self_from_instance_methods(self):
        methods = own_methods(Car)
        honk = next(m for m in methods if m["name"] == "honk")
        assert [p["name"] for p in honk["parameters"]] == ["times"]

    def test_strips_cls_from_classmethods(self):
        methods = own_methods(Car)
        from_name = next(m for m in methods if m["name"] == "from_name")
        assert [p["name"] for p in from_name["parameters"]] == ["name"]

    def test_does_not_strip_parameters_from_staticmethods(self):
        """staticmethodにはself/clsが元々付かないため、全パラメータをそのまま残す。"""

        class Sample:
            @staticmethod
            def add(a: int, b: int) -> int:
                return a + b

        methods = own_methods(Sample)
        add = methods[0]
        assert [p["name"] for p in add["parameters"]] == ["a", "b"]


class TestOwnMethodsTypeFormatting:
    """レビューフィードバック優先度2: 型表記の正規化。

    フィクスチャクラスはモジュールレベルに定義する(関数ローカルのクラスは
    qualnameに`<locals>`が混じり、モジュール修飾の除去とは別の関心事になるため)。
    """

    def test_strips_class_repr_wrapper_for_builtin_types(self):
        methods = own_methods(PriceSetter)
        method = methods[0]
        price_param = next(p for p in method["parameters"] if p["name"] == "price")
        assert price_param["type"] == "float"
        assert method["return_type"] == "bool"

    def test_format_type_passes_through_none_without_crashing(self):
        """ドッグフーディングで発見した回帰: py2pumlがUmlAttribute.type=Noneを返す
        ケースがあり、format_type(None)がTypeErrorでクラッシュしていた。
        """
        assert format_type(None) is None

    def test_strips_module_qualifiers_from_generic_types(self):
        methods = own_methods(ProductLister)
        add_products = next(m for m in methods if m["name"] == "add_products")
        products_param = next(p for p in add_products["parameters"] if p["name"] == "products")
        assert products_param["type"] == "List[Product]"

    def test_strips_module_qualifiers_from_optional_types(self):
        methods = own_methods(ProductLister)
        find = next(m for m in methods if m["name"] == "find")
        assert find["return_type"] == "Optional[Product]"


class Engine:
    pass


class HTTPAdapterLike:
    """requests.adapters.HTTPAdapter.max_retriesパターンの再現(実際に発生した回帰)。

    クラス本体で型だけ宣言し(`max_retries: Retry`。値の代入は無い)、`__init__`内で
    `self.max_retries = ...`と代入する、よくあるPythonのイディオム。
    """

    max_retries: "Retry"

    def __init__(self, max_retries: "Retry | None" = None):
        self.max_retries = max_retries


class Retry:
    pass


class AliasedTypingCar:
    """clickで実際に発生した回帰の再現: `import typing as t`というエイリアス付き
    importでの型注釈。py2puml本体はこれを解決できないが、get_type_hints()なら
    エイリアスに関係なくモジュールのglobalsに対して実際に評価するため解決できる。
    """

    parts: t.Dict[str, Engine]  # noqa: UP006 - エイリアス付きimportでのtyping.Dict使用を意図的に再現


@dataclass
class DataclassCar:
    engine: Engine


class NamedTupleLike(typing.NamedTuple):
    x: int
    y: int


class ConsoleLike:
    """richで実際に発生した回帰の再現: 循環import回避のためのTYPE_CHECKING限定
    importで、実行時に存在しない名前への文字列前方参照。get_type_hints()でも
    解決できないが、クラッシュせず型を文字列のまま返す(このクラスだけ縮退する)。
    """

    def __init__(self, live: "NotActuallyImportedAtRuntime" = None):  # noqa: F821
        self.live = live


class TestOwnAttributes:
    """属性の型解決(自前実装。HQ指摘・実戦テストの回帰対応)。

    py2puml本体はモジュールの実行時名前空間への`getattr()`で型注釈を解決するが、
    importのエイリアスやTYPE_CHECKING限定importが絡むとクラッシュ/解決失敗する
    (実戦テストでclick/rich/httpxに対して実際に発生)。design-diffはこの部分を
    py2pumlに任せず、標準ライブラリのtyping.get_type_hints()で自前解決する。
    """

    def test_merges_class_level_annotation_with_init_assignment(self):
        """requests.adapters.HTTPAdapter.max_retriesと同じパターンで、
        型注釈のみの宣言と__init__代入が別属性として重複しないこと。
        """
        attributes = own_attributes(HTTPAdapterLike)
        max_retries_attrs = [a for a in attributes if a["name"] == "max_retries"]
        assert len(max_retries_attrs) == 1

    def test_resolves_aliased_typing_import_via_get_type_hints(self):
        """clickの実際の回帰(import typing as t)。get_type_hints()ならエイリアス
        があっても正しく解決できる(py2puml本体のgetattr方式では失敗していた)。
        """
        attributes = own_attributes(AliasedTypingCar)
        parts = next(a for a in attributes if a["name"] == "parts")
        assert parts["type"] == "Dict[str, Engine]"

    def test_dataclass_fields_are_instance_attributes_not_static(self):
        """dataclassのクラスレベル注釈は、実体としてはインスタンス属性
        (static=False)。py2pumlのinspect_dataclass_typeと同じ扱いを維持する。
        """
        attributes = own_attributes(DataclassCar)
        engine = next(a for a in attributes if a["name"] == "engine")
        assert engine["static"] is False

    def test_old_style_namedtuple_fields_are_typed_as_any(self):
        import collections

        LegacyPoint = collections.namedtuple("LegacyPoint", ["x", "y"])
        attributes = own_attributes(LegacyPoint)
        names_and_types = {a["name"]: a["type"] for a in attributes}
        assert names_and_types == {"x": "Any", "y": "Any"}

    def test_typing_namedtuple_fields_use_their_own_annotations(self):
        attributes = own_attributes(NamedTupleLike)
        names_and_types = {a["name"]: a["type"] for a in attributes}
        assert names_and_types == {"x": "int", "y": "int"}

    def test_gracefully_degrades_when_forward_reference_is_unresolvable(self):
        """richの実際の回帰(TYPE_CHECKING限定importの文字列前方参照)の再現。
        解決できない型注釈でもクラッシュせず、このクラスだけ縮退する
        (型が取れる範囲の文字列で表示される)。
        """
        attributes = own_attributes(ConsoleLike)
        live = next(a for a in attributes if a["name"] == "live")
        assert live["name"] == "live"  # クラッシュせずここまで到達することが重要
