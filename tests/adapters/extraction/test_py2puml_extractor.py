"""Py2pumlExtractor の統合テスト。実際にpy2pumlとサブプロセスを使う(モックしない)。

architecture.md §5 の実測で確認した設計判断が実装でも守られていることを検証する:
- §5.2: symlink未解決パスでもクラスが消えないこと(.resolve()の効果)
- §5.3: 同一プロセス内で同じpackage名を2回extractしても衝突しないこと
         (サブプロセス分離のリグレッションテスト)
- §5.4 / HQ指摘1: 継承メソッドを拾わないこと(実際のpy2puml実行を通して)

テストごとに package 名を変えて、pytest プロセス内でのimportキャッシュ汚染を避ける
(design_diffプロセス自体はテスト間で共有されるため)。
"""

from pathlib import Path

import pytest

from design_diff.adapters.extraction.py2puml_extractor import Py2pumlExtractor
from design_diff.domain.model import RelationType


def write_package(root: Path, package: str, models_py: str) -> Path:
    pkg_dir = root
    for part in package.split("."):
        pkg_dir = pkg_dir / part
        pkg_dir.mkdir(parents=True, exist_ok=True)
        (pkg_dir / "__init__.py").touch()
    (pkg_dir / "models.py").write_text(models_py)
    return root


CAR_V1 = """
from dataclasses import dataclass
from typing import List


@dataclass
class Engine:
    horsepower: int


@dataclass
class Wheel:
    diameter: float


class Vehicle:
    def __init__(self, name: str):
        self.name: str = name

    def drive(self):
        pass


class Car(Vehicle):
    def __init__(self, name: str, engine: Engine):
        super().__init__(name)
        self.engine: Engine = engine
        self.wheels: List[Wheel] = []

    def honk(self):
        pass
"""

CAR_V2 = """
from dataclasses import dataclass


@dataclass
class Engine:
    horsepower: int


@dataclass
class Battery:
    capacity_kwh: float


class Vehicle:
    def __init__(self, name: str):
        self.name: str = name

    def drive(self):
        pass


class Car(Vehicle):
    def __init__(self, name: str, engine: Engine, battery: Battery):
        super().__init__(name)
        self.engine: Engine = engine
        self.battery: Battery = battery
"""


class TestPy2pumlExtractorBasics:
    def test_extracts_attributes_and_inheritance_and_composition(self, tmp_path):
        package = "extractor_basics_pkg"
        write_package(tmp_path, package, CAR_V1)

        snapshot = Py2pumlExtractor().extract(tmp_path, package)

        car = snapshot.classes[f"{package}.models.Car"]
        assert {a.name for a in car.attributes} == {"engine", "wheels"}
        relation_types_to_engine = {
            r.type for r in snapshot.relations if r.target_fqn == f"{package}.models.Engine"
        }
        assert RelationType.COMPOSITION in relation_types_to_engine
        inheritance = [r for r in snapshot.relations if r.type == RelationType.INHERITANCE]
        assert (f"{package}.models.Vehicle", f"{package}.models.Car") in [
            (r.source_fqn, r.target_fqn) for r in inheritance
        ]

    def test_own_methods_only_car_does_not_include_inherited_drive(self, tmp_path):
        """HQ指摘1回帰テスト(実プロセス経由)。"""
        package = "extractor_methods_pkg"
        write_package(tmp_path, package, CAR_V1)

        snapshot = Py2pumlExtractor().extract(tmp_path, package)

        car = snapshot.classes[f"{package}.models.Car"]
        method_names = {m.name for m in car.methods}
        assert method_names == {"__init__", "honk"}
        assert "drive" not in method_names

    def test_works_when_root_path_contains_unresolved_symlink(self, tmp_path):
        """§5.2の回帰テスト: symlink未解決パスでもクラスが消えないこと。"""
        real_root = tmp_path / "real_root"
        real_root.mkdir()
        package = "extractor_symlink_pkg"
        write_package(real_root, package, CAR_V1)

        symlinked_root = tmp_path / "symlinked_root"
        symlinked_root.symlink_to(real_root)

        snapshot = Py2pumlExtractor().extract(symlinked_root, package)

        assert f"{package}.models.Car" in snapshot.classes


class TestPy2pumlExtractorProcessIsolation:
    def test_extracting_same_package_name_twice_in_one_process_does_not_collide(self, tmp_path):
        """§5.3の回帰テスト(最重要): 同一プロセス内で同名パッケージを2回extractしても
        base/head両方とも正しく取得できること(サブプロセス分離が機能していることの証明)。
        """
        package = "extractor_isolation_pkg"

        base_root = tmp_path / "base"
        write_package(base_root, package, CAR_V1)

        head_root = tmp_path / "head"
        write_package(head_root, package, CAR_V2)

        extractor = Py2pumlExtractor()
        base_snapshot = extractor.extract(base_root, package)
        head_snapshot = extractor.extract(head_root, package)

        base_car = base_snapshot.classes[f"{package}.models.Car"]
        head_car = head_snapshot.classes[f"{package}.models.Car"]

        assert {a.name for a in base_car.attributes} == {"engine", "wheels"}
        assert {a.name for a in head_car.attributes} == {"engine", "battery"}
        assert f"{package}.models.Battery" in head_snapshot.classes
        assert f"{package}.models.Battery" not in base_snapshot.classes


class TestPy2pumlExtractorErrors:
    def test_raises_when_worker_fails(self, tmp_path):
        from design_diff.adapters.extraction.py2puml_extractor import Py2pumlExtractionError

        with pytest.raises(Py2pumlExtractionError):
            Py2pumlExtractor().extract(tmp_path / "does_not_exist", "nope")
