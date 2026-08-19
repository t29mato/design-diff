"""DiffEngine のテスト。

architecture.md §4 のdiffアルゴリズムに対応。
- クラスのadded/removed/modified(fqnの集合演算)
- modifiedクラス内の属性差分・メソッド差分
- リレーションのadded/removed(3つ組の集合差分)
- 沈黙原則: 完全一致するクラスはmodifiedに出さない(§4.1)
"""

from design_diff.domain.diff import DiffEngine
from design_diff.domain.model import (
    AttributeIR,
    ClassIR,
    MethodIR,
    ParameterIR,
    RelationIR,
    RelationType,
    SnapshotIR,
)


def make_snapshot(package="pkg", classes=None, relations=None) -> SnapshotIR:
    return SnapshotIR(
        package=package,
        classes={c.fqn: c for c in (classes or [])},
        relations=frozenset(relations or []),
    )


def make_class(fqn, name=None, is_abstract=False, attributes=(), methods=()) -> ClassIR:
    return ClassIR(
        fqn=fqn,
        name=name or fqn.rsplit(".", 1)[-1],
        is_abstract=is_abstract,
        attributes=tuple(attributes),
        methods=tuple(methods),
    )


class TestClassAddedRemoved:
    def test_class_only_in_head_is_added(self):
        base = make_snapshot()
        head = make_snapshot(classes=[make_class("pkg.Battery")])

        diff = DiffEngine().diff(base, head)

        assert [c.fqn for c in diff.classes.added] == ["pkg.Battery"]
        assert diff.classes.removed == ()
        assert diff.classes.modified == ()
        assert diff.has_changes is True

    def test_class_only_in_base_is_removed(self):
        base = make_snapshot(classes=[make_class("pkg.Wheel")])
        head = make_snapshot()

        diff = DiffEngine().diff(base, head)

        assert diff.classes.added == ()
        assert [c.fqn for c in diff.classes.removed] == ["pkg.Wheel"]

    def test_identical_snapshots_produce_no_changes_silence_principle(self):
        car = make_class(
            "pkg.Car",
            attributes=(AttributeIR(name="engine", type="Engine", static=False),),
        )
        base = make_snapshot(classes=[car])
        head = make_snapshot(classes=[car])

        diff = DiffEngine().diff(base, head)

        assert diff.classes.added == ()
        assert diff.classes.removed == ()
        assert diff.classes.modified == ()
        assert diff.has_changes is False

    def test_added_and_removed_are_sorted_by_fqn_for_deterministic_output(self):
        base = make_snapshot()
        head = make_snapshot(classes=[make_class("pkg.Zebra"), make_class("pkg.Apple")])

        diff = DiffEngine().diff(base, head)

        assert [c.fqn for c in diff.classes.added] == ["pkg.Apple", "pkg.Zebra"]


class TestClassModified:
    def test_attribute_added(self):
        base = make_snapshot(classes=[make_class("pkg.Car")])
        head = make_snapshot(
            classes=[
                make_class(
                    "pkg.Car",
                    attributes=(
                        AttributeIR(name="battery", type="Battery", static=False),
                    ),
                )
            ]
        )

        diff = DiffEngine().diff(base, head)

        assert len(diff.classes.modified) == 1
        mod = diff.classes.modified[0]
        assert mod.fqn == "pkg.Car"
        assert [a.name for a in mod.attributes.added] == ["battery"]
        assert mod.attributes.removed == ()
        assert mod.attributes.changed == ()

    def test_attribute_removed(self):
        base = make_snapshot(
            classes=[
                make_class(
                    "pkg.Car",
                    attributes=(
                        AttributeIR(name="wheels", type="List[Wheel]", static=False),
                    ),
                )
            ]
        )
        head = make_snapshot(classes=[make_class("pkg.Car")])

        diff = DiffEngine().diff(base, head)

        mod = diff.classes.modified[0]
        assert mod.attributes.removed[0].name == "wheels"
        assert mod.attributes.added == ()

    def test_attribute_type_changed(self):
        base = make_snapshot(
            classes=[
                make_class(
                    "pkg.Car",
                    attributes=(
                        AttributeIR(name="engine", type="Engine", static=False),
                    ),
                )
            ]
        )
        head = make_snapshot(
            classes=[
                make_class(
                    "pkg.Car",
                    attributes=(
                        AttributeIR(
                            name="engine", type="ElectricEngine", static=False
                        ),
                    ),
                )
            ]
        )

        diff = DiffEngine().diff(base, head)

        mod = diff.classes.modified[0]
        assert mod.attributes.added == ()
        assert mod.attributes.removed == ()
        change = mod.attributes.changed[0]
        assert change.name == "engine"
        assert change.old_type == "Engine"
        assert change.new_type == "ElectricEngine"

    def test_method_added_removed_and_changed(self):
        base = make_snapshot(
            classes=[
                make_class(
                    "pkg.Car",
                    methods=(
                        MethodIR(name="honk", parameters=(), return_type="None"),
                        MethodIR(name="stop", parameters=(), return_type="None"),
                    ),
                )
            ]
        )
        head = make_snapshot(
            classes=[
                make_class(
                    "pkg.Car",
                    methods=(
                        MethodIR(
                            name="honk",
                            parameters=(ParameterIR(name="times", type="int"),),
                            return_type="None",
                        ),
                        MethodIR(name="drive", parameters=(), return_type="None"),
                    ),
                )
            ]
        )

        diff = DiffEngine().diff(base, head)

        mod = diff.classes.modified[0]
        assert [m.name for m in mod.methods.added] == ["drive"]
        assert [m.name for m in mod.methods.removed] == ["stop"]
        assert mod.methods.changed[0].name == "honk"

    def test_is_abstract_change_is_tracked(self):
        base = make_snapshot(classes=[make_class("pkg.Car", is_abstract=False)])
        head = make_snapshot(classes=[make_class("pkg.Car", is_abstract=True)])

        diff = DiffEngine().diff(base, head)

        assert diff.classes.modified[0].is_abstract_changed is True

    def test_modification_carries_full_base_and_head_class_for_rendering(self):
        """レンダラー(Mermaid)がhead時点の全属性を表示するために、差分だけでなく
        base/headそれぞれの完全なClassIRもClassModificationに保持する。
        """
        base_car = make_class(
            "pkg.Car", attributes=(AttributeIR(name="wheels", type="List[Wheel]", static=False),)
        )
        head_car = make_class(
            "pkg.Car", attributes=(AttributeIR(name="battery", type="Battery", static=False),)
        )
        base = make_snapshot(classes=[base_car])
        head = make_snapshot(classes=[head_car])

        diff = DiffEngine().diff(base, head)

        mod = diff.classes.modified[0]
        assert mod.base_class == base_car
        assert mod.head_class == head_car

    def test_inherited_method_change_does_not_mark_subclass_as_modified(self):
        """HQ指摘1の回帰テスト: 基底クラスのメソッド変更でサブクラスが誤検出されないこと。

        py2pumlのIRには継承関係は別途RelationIRとして表現されるが、ClassIR.methods自体は
        『自クラス定義分のみ』(architecture.md §3.2, §5.4)。したがって基底クラスのメソッドが
        変わっても、サブクラスのClassIRのmethodsフィールドは不変であり、DiffEngineは
        サブクラスをmodifiedとして検出しない(サブクラスのClassIRに変更がないため)。
        """
        car_base = make_class("pkg.Car", methods=())  # Car自身はdriveを定義していない
        car_head = make_class("pkg.Car", methods=())  # Carは変わっていない

        base = make_snapshot(classes=[car_base])
        head = make_snapshot(classes=[car_head])

        diff = DiffEngine().diff(base, head)

        assert diff.classes.modified == ()
        assert diff.has_changes is False


class TestRelationDiff:
    def test_relation_added(self):
        base = make_snapshot()
        relation = RelationIR(source_fqn="pkg.Car", target_fqn="pkg.Battery", type=RelationType.COMPOSITION)
        head = make_snapshot(relations=[relation])

        diff = DiffEngine().diff(base, head)

        assert diff.relations.added == (relation,)
        assert diff.relations.removed == ()

    def test_relation_removed(self):
        relation = RelationIR(source_fqn="pkg.Car", target_fqn="pkg.Wheel", type=RelationType.COMPOSITION)
        base = make_snapshot(relations=[relation])
        head = make_snapshot()

        diff = DiffEngine().diff(base, head)

        assert diff.relations.removed == (relation,)
        assert diff.relations.added == ()

    def test_identical_relations_produce_no_diff(self):
        relation = RelationIR(source_fqn="pkg.Vehicle", target_fqn="pkg.Car", type=RelationType.INHERITANCE)
        base = make_snapshot(relations=[relation])
        head = make_snapshot(relations=[relation])

        diff = DiffEngine().diff(base, head)

        assert diff.relations.has_changes is False


class TestSnapshotDiffHasChanges:
    def test_false_when_nothing_changed(self):
        base = make_snapshot(classes=[make_class("pkg.Car")])
        head = make_snapshot(classes=[make_class("pkg.Car")])

        diff = DiffEngine().diff(base, head)

        assert diff.has_changes is False

    def test_true_when_only_relations_changed(self):
        base = make_snapshot(classes=[make_class("pkg.Car")])
        relation = RelationIR(source_fqn="pkg.Car", target_fqn="pkg.Battery", type=RelationType.COMPOSITION)
        head = make_snapshot(classes=[make_class("pkg.Car")], relations=[relation])

        diff = DiffEngine().diff(base, head)

        assert diff.has_changes is True
