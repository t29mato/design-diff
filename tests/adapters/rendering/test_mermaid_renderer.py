"""MermaidRenderer のテスト。architecture.md §7。

- 3状態(追加/削除/変更)をclassDefで色分け
- 変更のないクラスは出さない(ノイズ削減)
- リレーションはpy2puml/PlantUML互換の記法(*--, <|--)にマッピング
"""

from design_diff.adapters.rendering.mermaid_renderer import MermaidRenderer
from design_diff.domain.diff import (
    AttributeDiff,
    ClassDiff,
    ClassModification,
    MethodDiff,
    RelationDiff,
    SnapshotDiff,
)
from design_diff.domain.model import AttributeIR, ClassIR, MethodIR, RelationIR, RelationType

EMPTY_DIFF = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff())


def make_class(fqn, attributes=(), methods=(), is_abstract=False) -> ClassIR:
    return ClassIR(
        fqn=fqn, name=fqn.rsplit(".", 1)[-1], is_abstract=is_abstract, attributes=attributes, methods=methods
    )


class TestMermaidRendererStructure:
    def test_starts_with_class_diagram_header_and_style_defs(self):
        output = MermaidRenderer().render(EMPTY_DIFF)

        assert output.startswith("classDiagram")
        assert "classDef added" in output
        assert "classDef removed" in output
        assert "classDef modified" in output

    def test_ignores_the_mermaid_kwarg(self):
        """MermaidRenderer自身はRendererPortのmermaid/meta引数を無視してよい(§2)。"""
        output = MermaidRenderer().render(EMPTY_DIFF, mermaid="ignored", meta={"package": "pkg"})
        assert output.startswith("classDiagram")


class TestMermaidRendererAddedRemoved:
    def test_renders_added_class_with_added_style(self):
        added = make_class("pkg.Battery", attributes=(AttributeIR(name="capacity_kwh", type="float"),))
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "class `pkg.Battery`:::added" in output
        assert "capacity_kwh" in output
        assert "float" in output

    def test_renders_removed_class_with_removed_style(self):
        removed = make_class("pkg.Wheel", attributes=(AttributeIR(name="diameter", type="float"),))
        diff = SnapshotDiff(classes=ClassDiff(removed=(removed,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "class `pkg.Wheel`:::removed" in output

    def test_renders_methods_with_parameters_and_return_type(self):
        added = make_class(
            "pkg.Car",
            methods=(MethodIR(name="honk", parameters=(), return_type="None"),),
        )
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "honk()" in output
        assert "None" in output


class TestMermaidRendererModified:
    def test_renders_modified_class_with_modified_style_and_note(self):
        base_car = make_class("pkg.Car", attributes=(AttributeIR(name="wheels", type="List[Wheel]"),))
        head_car = make_class("pkg.Car", attributes=(AttributeIR(name="battery", type="Battery"),))
        mod = ClassModification(
            fqn="pkg.Car",
            name="Car",
            attributes=AttributeDiff(
                added=(AttributeIR(name="battery", type="Battery"),),
                removed=(AttributeIR(name="wheels", type="List[Wheel]"),),
            ),
            methods=MethodDiff(),
            base_class=base_car,
            head_class=head_car,
        )
        diff = SnapshotDiff(classes=ClassDiff(modified=(mod,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "class `pkg.Car`:::modified" in output
        assert "battery" in output  # head時点の属性を表示
        assert "note for `pkg.Car`" in output
        assert "+ battery" in output  # noteの中に差分サマリ
        assert "- wheels" in output


class TestMermaidRendererUnchanged:
    def test_unchanged_classes_are_not_part_of_the_diff_and_produce_no_extra_class_block(self):
        # SnapshotDiffには変更のあったクラスしか入ってこない前提(DiffEngineの沈黙原則)。
        # レンダラー側は空のClassDiffに対して余計なclassブロックを出さないことだけを保証する。
        output = MermaidRenderer().render(EMPTY_DIFF)
        assert "class `" not in output


class TestMermaidRendererRelations:
    def test_renders_added_composition(self):
        relation = RelationIR(source_fqn="pkg.Car", target_fqn="pkg.Battery", type=RelationType.COMPOSITION)
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(relation,)))

        output = MermaidRenderer().render(diff)

        assert "`pkg.Car` *-- `pkg.Battery`" in output

    def test_renders_added_inheritance(self):
        relation = RelationIR(source_fqn="pkg.Vehicle", target_fqn="pkg.Car", type=RelationType.INHERITANCE)
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(relation,)))

        output = MermaidRenderer().render(diff)

        assert "`pkg.Vehicle` <|-- `pkg.Car`" in output

    def test_marks_removed_relations_distinctly_from_added(self):
        added = RelationIR(source_fqn="pkg.Car", target_fqn="pkg.Battery", type=RelationType.COMPOSITION)
        removed = RelationIR(source_fqn="pkg.Car", target_fqn="pkg.Wheel", type=RelationType.COMPOSITION)
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(added,), removed=(removed,)))

        output = MermaidRenderer().render(diff)

        added_line = next(line for line in output.splitlines() if "pkg.Battery" in line)
        removed_line = next(line for line in output.splitlines() if "pkg.Wheel" in line)
        assert added_line != removed_line
        assert "removed" in removed_line or "%% removed" in output
