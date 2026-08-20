"""Py2pumlExtractor の統合テスト。実際にpy2pumlとサブプロセスを使う(モックしない)。

architecture.md §5 の実測で確認した設計判断が実装でも守られていることを検証する:
- §5.2: symlink未解決パスでもクラスが消えないこと(.resolve()の効果)
- §5.3: 同一プロセス内で同じpackage名を2回extractしても衝突しないこと
         (サブプロセス分離のリグレッションテスト)
- §5.4 / 指摘1: 継承メソッドを拾わないこと(実際のpy2puml実行を通して)

さらに、design-diff自身をdesign-diffで解析する「ドッグフーディング」(CLAUDE.md)を
実施した際に発見した回帰: src-layout(`src/<package>/...`)のリポジトリでは
`root / package` にパッケージが存在せず、`root / "src" / package` を見なければ
ならない。これを見落とすと「例外なく0クラス」という無言の失敗になる(§5.2の
symlink罠と同種の『無言で消える』クラスの罠)。

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
        """指摘1回帰テスト(実プロセス経由)。

        既定ではダンダーメソッド(__init__含む)も除外される
        (レビューフィードバック優先度1)。
        """
        package = "extractor_methods_pkg"
        write_package(tmp_path, package, CAR_V1)

        snapshot = Py2pumlExtractor().extract(tmp_path, package)

        car = snapshot.classes[f"{package}.models.Car"]
        method_names = {m.name for m in car.methods}
        assert method_names == {"honk"}
        assert "drive" not in method_names

    def test_include_dunder_opt_in_brings_back_init(self, tmp_path):
        package = "extractor_include_dunder_pkg"
        write_package(tmp_path, package, CAR_V1)

        snapshot = Py2pumlExtractor().extract(tmp_path, package, include_dunder=True)

        car = snapshot.classes[f"{package}.models.Car"]
        method_names = {m.name for m in car.methods}
        assert "__init__" in method_names
        assert "honk" in method_names

    def test_attribute_types_are_formatted_cleanly(self, tmp_path):
        """レビューフィードバック優先度2の回帰テスト(実プロセス経由)。"""
        package = "extractor_type_format_pkg"
        write_package(tmp_path, package, CAR_V1)

        snapshot = Py2pumlExtractor().extract(tmp_path, package)

        car = snapshot.classes[f"{package}.models.Car"]
        types_by_name = {a.name: a.type for a in car.attributes}
        assert types_by_name["engine"] == "Engine"
        assert types_by_name["wheels"] == "List[Wheel]"
        assert "<class" not in types_by_name["engine"]
        assert "typing." not in types_by_name["wheels"]

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

    def test_analyzing_a_package_literally_named_design_diff_does_not_collide_with_the_tool_itself(
        self, tmp_path
    ):
        """ドッグフーディング(design-diff自身にdesign-diffを掛ける)で発見した回帰テスト。

        ワーカーを `python -m design_diff.adapters.extraction._worker ...` で起動すると、
        その起動自体がツール自身のパッケージ `design_diff` を先にimportしてしまう。
        解析対象がたまたま同じ名前(`design_diff`)だと、Inspectorが対象ファイルを
        importしようとした時に sys.modules に既に載っている『ツール自身の
        design_diffパッケージ』(このリポジトリのsrc/)を再利用してしまい、
        対象ワークツリーのクラスが一つも見つからない(例外なく0クラス)。

        対策: ワーカーは `-m <dotted module>` ではなく、ファイルパスを直接指定して
        起動する。これにより起動時に `design_diff` パッケージのimportが発生しない。
        """
        package = "design_diff"  # ツール自身と同じ名前をあえて使う
        write_package(tmp_path, package, CAR_V1)

        snapshot = Py2pumlExtractor().extract(tmp_path, package)

        assert f"{package}.models.Car" in snapshot.classes
        assert f"{package}.models.Engine" in snapshot.classes


class TestPy2pumlExtractorSrcLayout:
    def test_extracts_classes_when_package_lives_under_src(self, tmp_path):
        """ドッグフーディング(CLAUDE.md)で発見した回帰テスト。

        design-diff自身のリポジトリのようにsrc-layout(`src/<package>/...`)の場合、
        `root / package` にはパッケージが存在しない。これを見落とすと py2puml の
        Inspector が root_domain_path を見つけられず、例外なく0クラスという
        『無言の失敗』になる(§5.2のsymlink罠と同種)。
        """
        package = "extractor_src_layout_pkg"
        write_package(tmp_path / "src", package, CAR_V1)

        snapshot = Py2pumlExtractor().extract(tmp_path, package)

        assert f"{package}.models.Car" in snapshot.classes
        assert f"{package}.models.Engine" in snapshot.classes


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


ALIASED_TYPING_IMPORT = """
import typing as t


class Engine:
    pass


class Car:
    parts: t.Dict[str, Engine]
"""

TYPE_CHECKING_FORWARD_REFERENCE = """
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from .live import Live


class Console:
    def __init__(self, live: Optional["Live"] = None):
        self.live = live
"""


class TestPy2pumlExtractorRealWorldRegressions:
    """実戦テスト(実在の外部パッケージ)で発見した回帰の、実際のサブプロセス経由
    (py2pumlの本物のInspectorを一部使う、実装全体)での再現テスト。

    以前はpy2puml本体の型解決ロジック(getattr方式)がこれらのパターンで解析全体を
    クラッシュさせていた。design-diffは属性の型解決をtyping.get_type_hints()による
    自前実装に置き換えたことで、クラッシュせず解析を完走できる
    (詳細: docs/design/investigations/py2puml-resolution-failures-root-cause.md)。
    """

    def test_aliased_typing_import_does_not_crash_extraction(self, tmp_path):
        """clickの実際の回帰(import typing as t)。以前はpy2puml本体が
        `Could not resolve type typing.Dict`というValueErrorで解析全体を落としていた。
        """
        package = "regression_aliased_pkg"
        write_package(tmp_path, package, ALIASED_TYPING_IMPORT)

        snapshot = Py2pumlExtractor().extract(tmp_path, package)

        car = snapshot.classes[f"{package}.models.Car"]
        parts = next(a for a in car.attributes if a.name == "parts")
        assert parts.type == "Dict[str, Engine]"
        composition_targets = {
            r.target_fqn for r in snapshot.relations if r.type == RelationType.COMPOSITION
        }
        assert f"{package}.models.Engine" in composition_targets

    def test_type_checking_forward_reference_degrades_gracefully(self, tmp_path):
        """richの実際の回帰(TYPE_CHECKING限定importの文字列前方参照)。以前は
        py2puml本体が`Optional["Live"] seems to be an invalid type annotation`と
        いうValueErrorで解析全体を落としていた。design-diffはクラッシュせず、
        Consoleクラス自体は完走する(liveの型は解決できず縮退する)。
        """
        package = "regression_forward_ref_pkg"
        write_package(tmp_path, package, TYPE_CHECKING_FORWARD_REFERENCE)

        snapshot = Py2pumlExtractor().extract(tmp_path, package)

        console = snapshot.classes[f"{package}.models.Console"]
        assert {a.name for a in console.attributes} == {"live"}
