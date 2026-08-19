"""py2pumlサブプロセスワーカー。architecture.md §5.3, §5.4。

1回の起動で1スナップショットだけを抽出する。base/headをまたいで同一プロセス内で
呼び出してはならない(sys.modulesキャッシュ衝突。§5.3の実測)。
Py2pumlExtractor がこのモジュールをサブプロセスとして起動し、プロセス分離を隠蔽する。

使い方:
    python -m design_diff.adapters.extraction._worker <root_path> <package>

標準出力にJSON({"package": ..., "classes": {...}, "relations": [...]})を1行で出力する。
"""

from __future__ import annotations

import importlib
import inspect
import json
import sys
from pathlib import Path

from py2puml.domain.inspection import Inspection
from py2puml.domain.umlclass import UmlClass
from py2puml.inspector import Inspector


def own_methods(cls: type) -> list[dict]:
    """clsが自分で定義したメソッドのみを抽出する(継承分は含まない)。

    HQ指摘1対応: inspect.getmembers(cls, predicate=isfunction)はMRO(継承元)を辿って
    基底クラスのメソッドまで返してしまうため使わない。vars(cls)(=cls.__dict__)を直接見て
    自クラス定義分のみに絞る。副産物としてclassmethodの取りこぼしも解消される
    (architecture.md §5.4で実測比較済み)。
    """
    methods: list[dict] = []
    for name, obj in vars(cls).items():
        if isinstance(obj, staticmethod):
            fn = obj.__func__
        elif isinstance(obj, classmethod):
            fn = obj.__func__
        elif inspect.isfunction(obj):
            fn = obj
        else:
            continue  # プロパティ・クラス変数などは対象外(属性側で別途扱う)

        try:
            signature = inspect.signature(fn)
        except (TypeError, ValueError):
            # C拡張など、シグネチャが取得できないものはスキップする
            continue

        parameters = [
            {
                "name": param.name,
                "type": None if param.annotation is inspect.Parameter.empty else str(param.annotation),
            }
            for param in signature.parameters.values()
        ]
        empty = inspect.Signature.empty
        return_type = None if signature.return_annotation is empty else str(signature.return_annotation)
        methods.append({"name": name, "parameters": parameters, "return_type": return_type})

    methods.sort(key=lambda m: m["name"])  # diffの安定性のため決定的な順序にする
    return methods


def class_object_for_fqn(fqn: str) -> type:
    """py2pumlのfqn(`<__module__>.<__name__>`)からクラスオブジェクトを再取得する。

    py2puml自体が `f'{definition_type.__module__}.{definition_type.__name__}'` という
    形式でfqnを作っている(py2puml/inspection/inspectmodule.py)ため、この形式に依存してよい。
    """
    module_name, class_name = fqn.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def extract_snapshot(root: Path, package: str) -> dict:
    # 罠1対策: symlink未解決だと対象クラスが無言で消える(architecture.md §5.2)。
    resolved_root = root.resolve()
    package_parts = package.split(".")

    # ドッグフーディングで発見した回帰(design-diff自身がsrc-layout):
    # `root / package` にパッケージが存在しない場合、`root / "src" / package` も試す。
    # どちらにも無ければ(存在しないパスのまま)Inspectorに渡し、Inspector自身の
    # フォールバック(モジュールとしてのimport)に委ねる。
    candidate = resolved_root.joinpath(*package_parts)
    src_candidate = resolved_root.joinpath("src", *package_parts)
    if not candidate.is_dir() and src_candidate.is_dir():
        candidate = src_candidate
    package_path = candidate

    inspection = Inspection({}, [])
    list(Inspector(resolved_root, package_path, package).inspect(inspection))

    classes: dict[str, dict] = {}
    for fqn, item in inspection.items_by_fqn.items():
        if not isinstance(item, UmlClass):
            continue  # Enumは対象外(architecture.md §3.5)
        try:
            cls = class_object_for_fqn(fqn)
            methods = own_methods(cls)
        except Exception:  # noqa: BLE001 - メソッド抽出はベストエフォート、失敗しても構造は返す
            methods = []
        classes[fqn] = {
            "fqn": fqn,
            "name": item.name,
            "is_abstract": item.is_abstract,
            "attributes": [{"name": a.name, "type": a.type, "static": a.static} for a in item.attributes],
            "methods": methods,
        }

    relations = [
        {"source_fqn": r.source_fqn, "target_fqn": r.target_fqn, "type": r.type.name.lower()}
        for r in inspection.relations
    ]

    return {"package": package, "classes": classes, "relations": relations}


def main() -> None:
    if len(sys.argv) != 3:
        usage = "usage: python -m design_diff.adapters.extraction._worker <root_path> <package>"
        print(usage, file=sys.stderr)
        sys.exit(2)
    root, package = Path(sys.argv[1]), sys.argv[2]
    payload = extract_snapshot(root, package)
    print(json.dumps(payload))


if __name__ == "__main__":
    main()
