"""JsonRenderer。RendererPortの実装。architecture.md §6(LLMO設計のJSONスキーマ)。

AIレビュアーがそのまま読める自己完結JSONを出力する。schema_versionはフィールド追加時
のみ変更し、破壊的変更ではmajorを上げる(§6)。

`warnings`(1.0→1.1、後方互換な追加): サブモジュールのimport失敗で解析が部分的に
しかできなかった場合、スキップしたモジュール名の一覧をここに載せる。空配列なら
解析はパッケージ全体を網羅している。
"""

from __future__ import annotations

import json

from design_diff.domain.diff import AttributeDiff, MethodDiff, SnapshotDiff
from design_diff.domain.model import AttributeIR, ClassIR, MethodIR, ParameterIR, RelationIR

SCHEMA_VERSION = "1.1"


def _attribute_to_dict(attribute: AttributeIR) -> dict:
    return {"name": attribute.name, "type": attribute.type, "static": attribute.static}


def _parameter_to_dict(parameter: ParameterIR) -> dict:
    return {"name": parameter.name, "type": parameter.type}


def _method_to_dict(method: MethodIR) -> dict:
    return {
        "name": method.name,
        "parameters": [_parameter_to_dict(p) for p in method.parameters],
        "return_type": method.return_type,
    }


def _class_to_dict(cls: ClassIR) -> dict:
    return {
        "fqn": cls.fqn,
        "name": cls.name,
        "is_abstract": cls.is_abstract,
        "attributes": [_attribute_to_dict(a) for a in cls.attributes],
        "methods": [_method_to_dict(m) for m in cls.methods],
    }


def _relation_to_dict(relation: RelationIR) -> dict:
    return {"source_fqn": relation.source_fqn, "target_fqn": relation.target_fqn, "type": relation.type.value}


def _attribute_diff_to_dict(diff: AttributeDiff) -> dict:
    return {
        "added": [_attribute_to_dict(a) for a in diff.added],
        "removed": [_attribute_to_dict(a) for a in diff.removed],
        "changed": [
            {"name": c.name, "old_type": c.old_type, "new_type": c.new_type} for c in diff.changed
        ],
    }


def _method_diff_to_dict(diff: MethodDiff) -> dict:
    return {
        "added": [_method_to_dict(m) for m in diff.added],
        "removed": [_method_to_dict(m) for m in diff.removed],
        "changed": [{"name": c.name} for c in diff.changed],
    }


class JsonRenderer:
    def render(
        self,
        diff: SnapshotDiff,
        *,
        mermaid: str | None = None,
        meta: dict[str, str] | None = None,
    ) -> str:
        meta = meta or {}
        payload = {
            "schema_version": SCHEMA_VERSION,
            "tool": "design-diff",
            "package": meta.get("package", ""),
            "base_ref": meta.get("base_ref", ""),
            "head_ref": meta.get("head_ref", ""),
            "has_changes": diff.has_changes,
            "warnings": list(diff.warnings),
            "summary": {
                "classes_added": len(diff.classes.added),
                "classes_removed": len(diff.classes.removed),
                "classes_modified": len(diff.classes.modified),
                "relations_added": len(diff.relations.added),
                "relations_removed": len(diff.relations.removed),
            },
            "classes": {
                "added": [_class_to_dict(c) for c in diff.classes.added],
                "removed": [_class_to_dict(c) for c in diff.classes.removed],
                "modified": [
                    {
                        "fqn": mod.fqn,
                        "name": mod.name,
                        "attributes": _attribute_diff_to_dict(mod.attributes),
                        "methods": _method_diff_to_dict(mod.methods),
                        "is_abstract_changed": mod.is_abstract_changed,
                    }
                    for mod in diff.classes.modified
                ],
            },
            "relations": {
                "added": [_relation_to_dict(r) for r in diff.relations.added],
                "removed": [_relation_to_dict(r) for r in diff.relations.removed],
            },
            "mermaid": f"```mermaid\n{mermaid}\n```" if mermaid is not None else "",
        }
        return json.dumps(payload, indent=2, ensure_ascii=False)
