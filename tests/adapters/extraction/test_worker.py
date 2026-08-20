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
from dataclasses import dataclass

from design_diff.adapters.extraction._worker import _dedupe_attributes, format_type, own_methods


@dataclass
class _RawAttribute:
    """py2pumlのUmlAttribute(name/type/static属性を持つ)の代役。実際のInspectorを
    経由せずに `_dedupe_attributes` を単体テストするために使う。
    """

    name: str
    type: str | None
    static: bool


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


class TestDedupeAttributes:
    """実運用パッケージ(requests.adapters.HTTPAdapter)を実際に解析して発見した回帰。

    クラス本体で型だけ宣言し(`max_retries: Retry`。値の代入は無い)、`__init__`内で
    `self.max_retries = ...` と代入する、よくあるPythonのイディオムに対し、py2pumlは
    同名の属性を「static=True(クラス本体の注釈)」と「static=False(インスタンス
    属性)」の2つの別属性として重複して返す。値の無いアノテーションは実体のある
    クラス属性を作らないため、design-diffの出力では1つにまとめるべき。
    """

    def test_merges_duplicate_names_preferring_the_instance_attribute(self):
        raw = [
            _RawAttribute(name="max_retries", type="Retry", static=True),
            _RawAttribute(name="max_retries", type="Retry", static=False),
        ]

        result = _dedupe_attributes(raw)

        assert result == [{"name": "max_retries", "type": "Retry", "static": False}]

    def test_keeps_distinct_names_untouched(self):
        raw = [
            _RawAttribute(name="a", type="int", static=False),
            _RawAttribute(name="b", type="str", static=True),
        ]

        result = _dedupe_attributes(raw)

        assert result == [
            {"name": "a", "type": "int", "static": False},
            {"name": "b", "type": "str", "static": True},
        ]

    def test_preserves_first_occurrence_order(self):
        raw = [
            _RawAttribute(name="z", type="int", static=False),
            _RawAttribute(name="a", type="int", static=False),
        ]

        result = _dedupe_attributes(raw)

        assert [a["name"] for a in result] == ["z", "a"]

    def test_normalizes_type_reprs_during_dedupe(self):
        """`_dedupe_attributes` は最終出力を作るので、format_typeの整形も適用する。"""
        raw = [_RawAttribute(name="price", type="<class 'float'>", static=False)]

        result = _dedupe_attributes(raw)

        assert result == [{"name": "price", "type": "float", "static": False}]
