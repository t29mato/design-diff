"""py2puml 技術検証スピーク(2026-08-19)

設計フェーズの前提となる実測を行うためのスクリプト。
本番コードではない — docs/design/architecture.md の根拠として残す。

検証内容:
  1. py2puml をライブラリとして呼び、継承・コンポジションが
     構造化データ(UmlClass / UmlRelation)として取得できるか
  2. base/head 2スナップショットを同一プロセス内で連続 inspect した場合に
     sys.modules のインポートキャッシュ衝突が起きるか

実行方法:
  uv run python docs/design/spikes/py2puml_verification.py

前提: 本リポジトリに `uv add py2puml` 済み(pyproject.toml 参照)。
このスクリプトは /tmp 配下にサンプルパッケージを2バージョン生成して使う。
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from py2puml.domain.inspection import Inspection
from py2puml.inspector import Inspector

SAMPLE_V1 = {
    "__init__.py": "",
    "models.py": '''
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Engine:
    horsepower: int


@dataclass
class Wheel:
    diameter: float


class Vehicle:
    """Base class with inheritance target."""
    def __init__(self, name: str):
        self.name: str = name


class Car(Vehicle):
    def __init__(self, name: str, engine: Engine):
        super().__init__(name)
        self.engine: Engine = engine
        self.wheels: List[Wheel] = []
        self.spare_wheel: Optional[Wheel] = None
''',
}

SAMPLE_V2 = {
    "__init__.py": "",
    "models.py": '''
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


class Car(Vehicle):
    def __init__(self, name: str, engine: Engine, battery: Battery):
        super().__init__(name)
        self.engine: Engine = engine
        self.battery: Battery = battery
''',
}


def write_sample(root: Path, files: dict[str, str]) -> Path:
    pkg = root / "sample"
    pkg.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (pkg / name).write_text(content)
    return pkg


def inspect_package(root: Path) -> Inspection:
    # ★重要: root は必ず .resolve() してから渡すこと。
    # Inspector は root_domain_path を内部で .resolve() するが、
    # sys.path に積む inspection_working_directory 側は呼び出し側の値をそのまま使うため、
    # 未解決のパス(例: macOS の /tmp -> /private/tmp, /var -> /private/var という
    # symlink)を渡すと、インポートされたモジュールの __file__ (未解決パス) と
    # root_domain_path (解決済みパス) が一致せず、
    # 対象クラスが「無言で(例外なく)」除外される。tempfile.TemporaryDirectory() は
    # macOS では /var/folders/... という未解決パスを返すため、この罠を踏みやすい。
    root = root.resolve()
    inspection = Inspection({}, [])
    # Inspector.inspect() は puml テキスト行を yield する generator だが、
    # 副作用として inspection.items_by_fqn / inspection.relations を構造化データで埋める。
    # -> 構造化データが主目的なら generator を list() で消費すれば良く、
    #    puml テキストへのパースは不要(検証1の結論)。
    list(Inspector(root, root / "sample", "sample").inspect(inspection))
    return inspection


def verify_structured_extraction() -> None:
    print("=== 検証1: ライブラリ組み込みで構造化データが取れるか ===")
    with tempfile.TemporaryDirectory() as tmp:
        root = write_sample(Path(tmp), SAMPLE_V1).parent
        inspection = inspect_package(root)

        for fqn, item in inspection.items_by_fqn.items():
            print(fqn, "->", item)
        for rel in inspection.relations:
            print(rel)
    print()


def verify_same_process_collision() -> None:
    print("=== 検証2: 同一プロセスで base/head を連続 inspect すると衝突するか ===")
    with tempfile.TemporaryDirectory() as tmp1, tempfile.TemporaryDirectory() as tmp2:
        base_root = write_sample(Path(tmp1), SAMPLE_V1).parent
        head_root = write_sample(Path(tmp2), SAMPLE_V2).parent

        insp_base = inspect_package(base_root)
        insp_head = inspect_package(head_root)

        print("base に Car は含まれるか:", "sample.models.Car" in insp_base.items_by_fqn)
        print("head に Car は含まれるか:", "sample.models.Car" in insp_head.items_by_fqn)

        if (
            "sample.models.Car" not in insp_head.items_by_fqn
            or "sample.models.Car" not in insp_base.items_by_fqn
        ):
            print(
                "-> 'sample.models' という同一のモジュール名を同一プロセス内で複数回"
                " import_module() すると、2回目以降は sys.modules のキャッシュが返る。"
                " キャッシュされたモジュールの __file__ は最初に import した時点のパスのままなので、"
                " 後続の inspect が期待する root_domain_path と一致せずフィルタで除外され、"
                " クラスが例外なく静かに消える(このスクリプトでは検証1が先に"
                " 'sample.models' を import 済みのため base の時点で既に汚染されている)。"
                " => base/head の抽出は必ずプロセス分離(サブプロセスや別インタプリタ起動)して"
                " 行うこと。同一プロセス内での連続 inspect は不可。"
            )
    print()


if __name__ == "__main__":
    verify_structured_extraction()
    verify_same_process_collision()
