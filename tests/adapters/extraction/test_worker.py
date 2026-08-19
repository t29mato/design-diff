"""ワーカー内部ロジック(own_methods等)の単体テスト。サブプロセスを介さず高速に検証する。

HQ指摘1の回帰テスト(architecture.md §5.4)を含む:
1. 継承したメソッドを拾わないこと
2. staticmethod/classmethodを取りこぼさないこと

さらにHQフィードバック(表示品質)の回帰テスト:
3. ダンダーメソッド(__init__/__eq__/__repr__/__hash__/__subclasshook__等)は既定で除外
   (dataclass自動生成やProtocolのノイズ、および属性差分との二重計上を防ぐ)。
   include_dunder=True で明示的に含められる(--include-dunder相当)。
4. 型表記の正規化: `<class 'float'>` は `float` に、`typing.List[pkg.models.Product]` は
   `List[Product]` に、モジュール修飾を剥がして読める形にする。
"""

import typing

from design_diff.adapters.extraction._worker import own_methods


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
        assert "drive" not in names, "継承元Vehicleのdriveを拾ってはいけない(HQ指摘1)"

    def test_includes_own_instance_method_with_signature(self):
        methods = own_methods(Car)
        honk = next(m for m in methods if m["name"] == "honk")
        param_names = [p["name"] for p in honk["parameters"]]
        assert param_names == ["self", "times"]
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
    """HQフィードバック優先度1: ダンダーメソッドの除外。"""

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


class TestOwnMethodsTypeFormatting:
    """HQフィードバック優先度2: 型表記の正規化。

    フィクスチャクラスはモジュールレベルに定義する(関数ローカルのクラスは
    qualnameに`<locals>`が混じり、モジュール修飾の除去とは別の関心事になるため)。
    """

    def test_strips_class_repr_wrapper_for_builtin_types(self):
        methods = own_methods(PriceSetter)
        method = methods[0]
        price_param = next(p for p in method["parameters"] if p["name"] == "price")
        assert price_param["type"] == "float"
        assert method["return_type"] == "bool"

    def test_strips_module_qualifiers_from_generic_types(self):
        methods = own_methods(ProductLister)
        add_products = next(m for m in methods if m["name"] == "add_products")
        products_param = next(p for p in add_products["parameters"] if p["name"] == "products")
        assert products_param["type"] == "List[Product]"

    def test_strips_module_qualifiers_from_optional_types(self):
        methods = own_methods(ProductLister)
        find = next(m for m in methods if m["name"] == "find")
        assert find["return_type"] == "Optional[Product]"
