"""差分アルゴリズム。architecture.md §4。

DiffEngine はどのポートも呼ばない純粋なロジックであり、SnapshotIR を2つ受け取って
SnapshotDiff を返すだけ(HQ指摘2により、ポートはapplication層に移設済み)。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from design_diff.domain.model import AttributeIR, ClassIR, MethodIR, RelationIR, SnapshotIR


@dataclass(frozen=True)
class AttributeChange:
    name: str
    old_type: str
    new_type: str
    old_static: bool
    new_static: bool


@dataclass(frozen=True)
class AttributeDiff:
    added: tuple[AttributeIR, ...] = ()
    removed: tuple[AttributeIR, ...] = ()
    changed: tuple[AttributeChange, ...] = ()

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)


@dataclass(frozen=True)
class MethodChange:
    name: str
    old: MethodIR
    new: MethodIR


@dataclass(frozen=True)
class MethodDiff:
    added: tuple[MethodIR, ...] = ()
    removed: tuple[MethodIR, ...] = ()
    changed: tuple[MethodChange, ...] = ()

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.changed)


@dataclass(frozen=True)
class ClassModification:
    fqn: str
    name: str
    attributes: AttributeDiff
    methods: MethodDiff
    # レンダラー(Mermaid等)がhead時点の全属性を表示できるよう、差分だけでなく
    # base/headそれぞれの完全なClassIRも保持する。
    base_class: ClassIR
    head_class: ClassIR
    is_abstract_changed: bool = False


@dataclass(frozen=True)
class ClassDiff:
    added: tuple[ClassIR, ...] = ()
    removed: tuple[ClassIR, ...] = ()
    modified: tuple[ClassModification, ...] = ()

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed or self.modified)


@dataclass(frozen=True)
class RelationDiff:
    added: tuple[RelationIR, ...] = ()
    removed: tuple[RelationIR, ...] = ()

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.removed)


@dataclass(frozen=True)
class SnapshotDiff:
    classes: ClassDiff
    relations: RelationDiff

    @property
    def has_changes(self) -> bool:
        return self.classes.has_changes or self.relations.has_changes


def _relation_sort_key(relation: RelationIR) -> tuple[str, str, str]:
    return (relation.source_fqn, relation.target_fqn, relation.type.value)


class DiffEngine:
    """base/head の SnapshotIR を突き合わせて SnapshotDiff を算出する。"""

    def diff(self, base: SnapshotIR, head: SnapshotIR) -> SnapshotDiff:
        return SnapshotDiff(
            classes=self._diff_classes(base.classes, head.classes),
            relations=self._diff_relations(base.relations, head.relations),
        )

    def _diff_classes(self, base: Mapping[str, ClassIR], head: Mapping[str, ClassIR]) -> ClassDiff:
        base_fqns = set(base.keys())
        head_fqns = set(head.keys())

        added = tuple(head[fqn] for fqn in sorted(head_fqns - base_fqns))
        removed = tuple(base[fqn] for fqn in sorted(base_fqns - head_fqns))

        modified = []
        for fqn in sorted(base_fqns & head_fqns):
            base_class, head_class = base[fqn], head[fqn]
            # 完全一致するクラスは出力しない(沈黙原則。§4.1)
            if base_class == head_class:
                continue
            modified.append(
                ClassModification(
                    fqn=fqn,
                    name=head_class.name,
                    attributes=self._diff_attributes(base_class.attributes, head_class.attributes),
                    methods=self._diff_methods(base_class.methods, head_class.methods),
                    base_class=base_class,
                    head_class=head_class,
                    is_abstract_changed=base_class.is_abstract != head_class.is_abstract,
                )
            )

        return ClassDiff(added=added, removed=removed, modified=tuple(modified))

    def _diff_attributes(
        self, base_attrs: tuple[AttributeIR, ...], head_attrs: tuple[AttributeIR, ...]
    ) -> AttributeDiff:
        base_by_name = {a.name: a for a in base_attrs}
        head_by_name = {a.name: a for a in head_attrs}
        base_names = set(base_by_name)
        head_names = set(head_by_name)

        added = tuple(head_by_name[name] for name in sorted(head_names - base_names))
        removed = tuple(base_by_name[name] for name in sorted(base_names - head_names))

        changed = []
        for name in sorted(base_names & head_names):
            b, h = base_by_name[name], head_by_name[name]
            if b.type != h.type or b.static != h.static:
                changed.append(
                    AttributeChange(
                        name=name, old_type=b.type, new_type=h.type, old_static=b.static, new_static=h.static
                    )
                )

        return AttributeDiff(added=added, removed=removed, changed=tuple(changed))

    def _diff_methods(
        self, base_methods: tuple[MethodIR, ...], head_methods: tuple[MethodIR, ...]
    ) -> MethodDiff:
        base_by_name = {m.name: m for m in base_methods}
        head_by_name = {m.name: m for m in head_methods}
        base_names = set(base_by_name)
        head_names = set(head_by_name)

        added = tuple(head_by_name[name] for name in sorted(head_names - base_names))
        removed = tuple(base_by_name[name] for name in sorted(base_names - head_names))

        changed = []
        for name in sorted(base_names & head_names):
            b, h = base_by_name[name], head_by_name[name]
            if b != h:
                changed.append(MethodChange(name=name, old=b, new=h))

        return MethodDiff(added=added, removed=removed, changed=tuple(changed))

    def _diff_relations(
        self, base_relations: frozenset[RelationIR], head_relations: frozenset[RelationIR]
    ) -> RelationDiff:
        added = tuple(sorted(head_relations - base_relations, key=_relation_sort_key))
        removed = tuple(sorted(base_relations - head_relations, key=_relation_sort_key))
        return RelationDiff(added=added, removed=removed)
