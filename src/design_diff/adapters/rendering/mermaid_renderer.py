"""MermaidRenderer。RendererPortの実装。architecture.md §7。

- 3状態を classDef + cssClass で色分け: 追加=緑、削除=赤、変更=黄
- modified クラスは head 時点の全属性/メソッドを表示し、差分サマリを note で添える
  (Mermaidの `+`/`-` は可視性(public/private)の意味で予約されているため、
  診断結果の追加/削除をメンバー行の先頭に流用しない。noteの中はプレーンテキストなので
  git diff風の `+`/`-` を安全に使える)
- 変更のないクラスは出さない(ノイズ削減)
- リレーションは `A *-- B`(コンポジション)/ `A <|-- B`(継承)にマッピング。
  removed relationは末尾に `%% removed` を付けて区別する
"""

from __future__ import annotations

from design_diff.domain.diff import AttributeDiff, ClassModification, MethodDiff, SnapshotDiff
from design_diff.domain.model import AttributeIR, ClassIR, MethodIR, RelationIR, RelationType

_CLASS_DEFS = (
    "    classDef added fill:#e6ffed,stroke:#22863a,color:#22863a",
    "    classDef removed fill:#ffeef0,stroke:#b31d28,color:#b31d28",
    "    classDef modified fill:#fff8e6,stroke:#b08800,color:#7a5c00",
)

_RELATION_ARROW = {
    RelationType.COMPOSITION: "*--",
    RelationType.INHERITANCE: "<|--",
}


def _quote(fqn: str) -> str:
    return f"`{fqn}`"


def _render_attribute_line(attribute: AttributeIR) -> str:
    return f"        +{attribute.name}: {attribute.type}"


def _render_method_line(method: MethodIR) -> str:
    params = ", ".join(f"{p.name}: {p.type}" if p.type else p.name for p in method.parameters)
    signature = f"        +{method.name}({params})"
    if method.return_type:
        signature += f": {method.return_type}"
    return signature


def _render_class_block(cls: ClassIR, style: str) -> list[str]:
    lines = [f"    class {_quote(cls.fqn)}:::{style} {{"]
    lines.extend(_render_attribute_line(a) for a in cls.attributes)
    lines.extend(_render_method_line(m) for m in cls.methods)
    lines.append("    }")
    return lines


def _format_attribute_diff_note(diff: AttributeDiff) -> list[str]:
    lines = [f"+ {a.name}: {a.type}" for a in diff.added]
    lines += [f"- {a.name}: {a.type}" for a in diff.removed]
    lines += [f"~ {c.name}: {c.old_type} -> {c.new_type}" for c in diff.changed]
    return lines


def _format_method_diff_note(diff: MethodDiff) -> list[str]:
    lines = [f"+ {m.name}()" for m in diff.added]
    lines += [f"- {m.name}()" for m in diff.removed]
    lines += [f"~ {c.name}()" for c in diff.changed]
    return lines


def _render_modification_block(mod: ClassModification) -> list[str]:
    lines = _render_class_block(mod.head_class, "modified")
    note_lines = _format_attribute_diff_note(mod.attributes) + _format_method_diff_note(mod.methods)
    if mod.is_abstract_changed:
        note_lines.append("~ is_abstract changed")
    note_text = "\\n".join(note_lines)
    lines.append(f'    note for {_quote(mod.fqn)} "{note_text}"')
    return lines


def _render_relation_line(relation: RelationIR, *, removed: bool) -> str:
    arrow = _RELATION_ARROW[relation.type]
    line = f"    {_quote(relation.source_fqn)} {arrow} {_quote(relation.target_fqn)}"
    if removed:
        line += "  %% removed"
    return line


class MermaidRenderer:
    def render(
        self,
        diff: SnapshotDiff,
        *,
        mermaid: str | None = None,
        meta: dict[str, str] | None = None,
    ) -> str:
        lines = ["classDiagram", *_CLASS_DEFS, ""]

        for cls in diff.classes.added:
            lines.extend(_render_class_block(cls, "added"))
        for cls in diff.classes.removed:
            lines.extend(_render_class_block(cls, "removed"))
        for mod in diff.classes.modified:
            lines.extend(_render_modification_block(mod))

        for relation in diff.relations.added:
            lines.append(_render_relation_line(relation, removed=False))
        for relation in diff.relations.removed:
            lines.append(_render_relation_line(relation, removed=True))

        return "\n".join(lines)
