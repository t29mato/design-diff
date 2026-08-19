"""Py2pumlExtractor。architecture.md §5.3, §5.4。ExtractorPortの実装。

base/headは必ず別プロセスで抽出する(このアダプタが内部でサブプロセス分離を隠蔽する)。
application.ports.ExtractorPort を import しない(§2.2: 構造的部分型で満たす)。
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from design_diff.domain.model import (
    AttributeIR,
    ClassIR,
    MethodIR,
    ParameterIR,
    RelationIR,
    RelationType,
    SnapshotIR,
)

# ドッグフーディングで発見した回帰: `python -m design_diff.adapters.extraction._worker`
# で起動すると、起動そのものがツール自身のパッケージ`design_diff`を先にimportしてしまう。
# 解析対象がたまたま`design_diff`という名前(=自分自身)だと、Inspectorが対象ファイルを
# importする際にsys.modulesに載っている「ツール自身のdesign_diff」を再利用してしまい、
# 対象ワークツリーのクラスが例外なく0件になる。
# 対策: `-m <dotted module>`ではなくワーカーの.pyをファイルパスで直接起動する。
# _worker.py自身はdesign_diffパッケージを一切importしないため、これで起動時の
# design_diff importが完全になくなり、対象パッケージが何であっても衝突しない。
_WORKER_SCRIPT = Path(__file__).parent / "_worker.py"


class Py2pumlExtractionError(RuntimeError):
    """ワーカーサブプロセスの実行に失敗した場合。"""


class Py2pumlExtractor:
    def extract(self, path: Path, package: str, *, include_dunder: bool = False) -> SnapshotIR:
        args = [sys.executable, str(_WORKER_SCRIPT), str(path), package]
        if include_dunder:
            args.append("--include-dunder")
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            raise Py2pumlExtractionError(
                f"py2puml worker failed for path={path} package={package}: {result.stderr.strip()}"
            )
        payload = json.loads(result.stdout)
        return self._to_snapshot_ir(payload)

    def _to_snapshot_ir(self, payload: dict) -> SnapshotIR:
        classes = {
            fqn: ClassIR(
                fqn=class_payload["fqn"],
                name=class_payload["name"],
                is_abstract=class_payload["is_abstract"],
                attributes=tuple(
                    AttributeIR(name=a["name"], type=a["type"], static=a["static"])
                    for a in class_payload["attributes"]
                ),
                methods=tuple(
                    MethodIR(
                        name=m["name"],
                        parameters=tuple(
                            ParameterIR(name=p["name"], type=p["type"]) for p in m["parameters"]
                        ),
                        return_type=m["return_type"],
                    )
                    for m in class_payload["methods"]
                ),
            )
            for fqn, class_payload in payload["classes"].items()
        }

        relations = frozenset(
            RelationIR(source_fqn=r["source_fqn"], target_fqn=r["target_fqn"], type=RelationType(r["type"]))
            for r in payload["relations"]
        )

        return SnapshotIR(package=payload["package"], classes=classes, relations=relations)
