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
"""

from __future__ import annotations

import importlib
import inspect
import json
import re
import sys
from pathlib import Path

from py2puml.domain.inspection import Inspection
from py2puml.domain.umlclass import UmlClass
from py2puml.inspector import Inspector

# HQフィードバック(表示品質)優先度1: ダンダーメソッドは既定で除外する。
# dataclassが自動生成する __init__/__eq__/__repr__/__hash__ や、typing.Protocolが
# 自動生成する __subclasshook__ が全クラスに並び図がノイズだらけになる上、
# フィールドを1つ足すたびに __init__ が「変更されたメソッド」として報告され、
# 属性差分(AttributeDiff)と二重計上される。--include-dunder相当のopt-inは残す。
_DUNDER_RE = re.compile(r"^__.+__$")

# HQフィードバック優先度2: 型表記の正規化。
# `<class 'float'>` や `typing.List[pkg.models.Product]` という生のreprを
# `float` / `List[Product]` のような読める形に整形する。
_CLASS_REPR_RE = re.compile(r"<(?:class|enum) '([\w.]+)'>")
_DOTTED_NAME_RE = re.compile(r"\b(?:[A-Za-z_][\w]*\.)+([A-Za-z_]\w*)\b")


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

    HQ指摘1対応: inspect.getmembers(cls, predicate=isfunction)はMRO(継承元)を辿って
    基底クラスのメソッドまで返してしまうため使わない。vars(cls)(=cls.__dict__)を直接見て
    自クラス定義分のみに絞る。副産物としてclassmethodの取りこぼしも解消される
    (architecture.md §5.4で実測比較済み)。

    `include_dunder=False`(既定)ではダンダーメソッド(`__xxx__`)を除外する
    (HQフィードバック優先度1)。
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


def class_object_for_fqn(fqn: str) -> type:
    """py2pumlのfqn(`<__module__>.<__name__>`)からクラスオブジェクトを再取得する。

    py2puml自体が `f'{definition_type.__module__}.{definition_type.__name__}'` という
    形式でfqnを作っている(py2puml/inspection/inspectmodule.py)ため、この形式に依存してよい。
    """
    module_name, class_name = fqn.rsplit(".", 1)
    module = importlib.import_module(module_name)
    return getattr(module, class_name)


def extract_snapshot(root: Path, package: str, *, include_dunder: bool = False) -> dict:
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
            methods = own_methods(cls, include_dunder=include_dunder)
        except Exception:  # noqa: BLE001 - メソッド抽出はベストエフォート、失敗しても構造は返す
            methods = []
        classes[fqn] = {
            "fqn": fqn,
            "name": item.name,
            "is_abstract": item.is_abstract,
            "attributes": [
                {"name": a.name, "type": format_type(a.type), "static": a.static} for a in item.attributes
            ],
            "methods": methods,
        }

    relations = [
        {"source_fqn": r.source_fqn, "target_fqn": r.target_fqn, "type": r.type.name.lower()}
        for r in inspection.relations
    ]

    return {"package": package, "classes": classes, "relations": relations}


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
