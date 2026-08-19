"""ワーカー内部ロジック(own_methods等)の単体テスト。サブプロセスを介さず高速に検証する。

HQ指摘1の回帰テスト(architecture.md §5.4)を含む:
1. 継承したメソッドを拾わないこと
2. staticmethod/classmethodを取りこぼさないこと
"""

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

    def test_base_class_own_methods_unaffected_by_subclass(self):
        methods = own_methods(Vehicle)
        names = {m["name"] for m in methods}
        assert names == {"__init__", "drive"}

    def test_methods_are_sorted_for_deterministic_output(self):
        methods = own_methods(Car)
        names = [m["name"] for m in methods]
        assert names == sorted(names)
