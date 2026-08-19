"""ドメインIR(中間表現)のテスト。

architecture.md §3 のスキーマ設計に対応。dataclassの構造的等価性・不変性(frozen)を
DiffEngineが前提にしているため、ここで担保する。
"""

import pytest

from design_diff.domain.model import (
    AttributeIR,
    ClassIR,
    MethodIR,
    ParameterIR,
    RelationIR,
    RelationType,
    SnapshotIR,
)


class TestAttributeIR:
    def test_equal_when_same_fields(self):
        a = AttributeIR(name="engine", type="Engine", static=False)
        b = AttributeIR(name="engine", type="Engine", static=False)
        assert a == b

    def test_not_equal_when_type_differs(self):
        a = AttributeIR(name="engine", type="Engine", static=False)
        b = AttributeIR(name="engine", type="ElectricEngine", static=False)
        assert a != b

    def test_is_frozen(self):
        a = AttributeIR(name="engine", type="Engine", static=False)
        with pytest.raises(AttributeError):
            a.type = "Other"  # type: ignore[misc]


class TestMethodIR:
    def test_equal_when_same_parameters_and_return_type(self):
        m1 = MethodIR(
            name="drive",
            parameters=(ParameterIR(name="self"), ParameterIR(name="speed", type="int")),
            return_type="None",
        )
        m2 = MethodIR(
            name="drive",
            parameters=(ParameterIR(name="self"), ParameterIR(name="speed", type="int")),
            return_type="None",
        )
        assert m1 == m2

    def test_not_equal_when_signature_differs(self):
        m1 = MethodIR(name="drive", parameters=(ParameterIR(name="self"),), return_type="None")
        m2 = MethodIR(
            name="drive",
            parameters=(ParameterIR(name="self"), ParameterIR(name="speed", type="int")),
            return_type="None",
        )
        assert m1 != m2


class TestClassIR:
    def test_fqn_is_the_identity_used_for_equality_together_with_structure(self):
        c1 = ClassIR(fqn="pkg.Car", name="Car", is_abstract=False, attributes=(), methods=())
        c2 = ClassIR(fqn="pkg.Car", name="Car", is_abstract=False, attributes=(), methods=())
        assert c1 == c2

    def test_not_equal_when_attributes_differ(self):
        c1 = ClassIR(
            fqn="pkg.Car",
            name="Car",
            is_abstract=False,
            attributes=(AttributeIR(name="engine", type="Engine", static=False),),
            methods=(),
        )
        c2 = ClassIR(fqn="pkg.Car", name="Car", is_abstract=False, attributes=(), methods=())
        assert c1 != c2


class TestRelationIR:
    def test_equal_relations_by_triple(self):
        r1 = RelationIR(source_fqn="pkg.Car", target_fqn="pkg.Engine", type=RelationType.COMPOSITION)
        r2 = RelationIR(source_fqn="pkg.Car", target_fqn="pkg.Engine", type=RelationType.COMPOSITION)
        assert r1 == r2

    def test_hashable_for_set_based_diffing(self):
        r1 = RelationIR(source_fqn="pkg.Car", target_fqn="pkg.Engine", type=RelationType.COMPOSITION)
        r2 = RelationIR(source_fqn="pkg.Car", target_fqn="pkg.Engine", type=RelationType.COMPOSITION)
        # frozenset化してdiffするため、内容が同じRelationIRは同一ハッシュでなければならない
        assert {r1} == {r2}
        assert len({r1, r2}) == 1


class TestSnapshotIR:
    def test_holds_classes_by_fqn_and_relations_as_frozenset(self):
        car = ClassIR(fqn="pkg.Car", name="Car", is_abstract=False, attributes=(), methods=())
        relation = RelationIR(source_fqn="pkg.Car", target_fqn="pkg.Engine", type=RelationType.COMPOSITION)
        snapshot = SnapshotIR(
            package="pkg",
            classes={"pkg.Car": car},
            relations=frozenset({relation}),
        )
        assert snapshot.classes["pkg.Car"] is car
        assert relation in snapshot.relations
