"""JsonRenderer のテスト。architecture.md §6(LLMO設計のJSONスキーマ)。"""

import json

from design_diff.adapters.rendering.json_renderer import JsonRenderer
from design_diff.domain.diff import (
    AttributeDiff,
    ClassDiff,
    ClassModification,
    MethodDiff,
    RelationDiff,
    SnapshotDiff,
)
from design_diff.domain.model import AttributeIR, ClassIR, MethodIR, ParameterIR, RelationIR, RelationType


def make_class(fqn, attributes=(), methods=()) -> ClassIR:
    return ClassIR(fqn=fqn, name=fqn.rsplit(".", 1)[-1], attributes=attributes, methods=methods)


EMPTY_DIFF = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff())
META = {"package": "pkg", "base_ref": "main", "head_ref": "feature"}


class TestJsonRendererTopLevelFields:
    def test_includes_schema_version_and_tool(self):
        payload = json.loads(JsonRenderer().render(EMPTY_DIFF, meta=META))
        assert payload["schema_version"] == "1.0"
        assert payload["tool"] == "design-diff"

    def test_includes_package_and_refs_from_meta(self):
        payload = json.loads(JsonRenderer().render(EMPTY_DIFF, meta=META))
        assert payload["package"] == "pkg"
        assert payload["base_ref"] == "main"
        assert payload["head_ref"] == "feature"

    def test_has_changes_false_for_empty_diff(self):
        payload = json.loads(JsonRenderer().render(EMPTY_DIFF, meta=META))
        assert payload["has_changes"] is False

    def test_has_changes_true_when_class_added(self):
        diff = SnapshotDiff(classes=ClassDiff(added=(make_class("pkg.Battery"),)), relations=RelationDiff())
        payload = json.loads(JsonRenderer().render(diff, meta=META))
        assert payload["has_changes"] is True

    def test_embeds_rendered_mermaid_as_fenced_block(self):
        payload = json.loads(JsonRenderer().render(EMPTY_DIFF, mermaid="classDiagram", meta=META))
        assert payload["mermaid"] == "```mermaid\nclassDiagram\n```"

    def test_meta_is_optional_and_produces_empty_strings(self):
        payload = json.loads(JsonRenderer().render(EMPTY_DIFF))
        assert payload["package"] == ""
        assert payload["base_ref"] == ""
        assert payload["head_ref"] == ""


class TestJsonRendererSummary:
    def test_summary_counts_added_removed_modified_classes_and_relations(self):
        added_relation = RelationIR(
            source_fqn="pkg.Car",
            target_fqn="pkg.Battery",
            type=RelationType.COMPOSITION,
        )
        removed_relation = RelationIR(
            source_fqn="pkg.Car",
            target_fqn="pkg.Wheel",
            type=RelationType.COMPOSITION,
        )
        mod = ClassModification(
            fqn="pkg.Car",
            name="Car",
            attributes=AttributeDiff(added=(AttributeIR(name="battery", type="Battery"),)),
            methods=MethodDiff(),
            base_class=make_class("pkg.Car"),
            head_class=make_class("pkg.Car", attributes=(AttributeIR(name="battery", type="Battery"),)),
        )
        diff = SnapshotDiff(
            classes=ClassDiff(
                added=(make_class("pkg.Battery"),),
                removed=(make_class("pkg.Wheel"),),
                modified=(mod,),
            ),
            relations=RelationDiff(
                added=(added_relation,),
                removed=(removed_relation,),
            ),
        )

        payload = json.loads(JsonRenderer().render(diff, meta=META))

        assert payload["summary"] == {
            "classes_added": 1,
            "classes_removed": 1,
            "classes_modified": 1,
            "relations_added": 1,
            "relations_removed": 1,
        }


class TestJsonRendererClasses:
    def test_added_class_includes_attributes_and_methods(self):
        cls = make_class("pkg.Battery", attributes=(AttributeIR(name="capacity_kwh", type="float"),))
        diff = SnapshotDiff(classes=ClassDiff(added=(cls,)), relations=RelationDiff())

        payload = json.loads(JsonRenderer().render(diff, meta=META))

        assert payload["classes"]["added"] == [
            {
                "fqn": "pkg.Battery",
                "name": "Battery",
                "is_abstract": False,
                "attributes": [{"name": "capacity_kwh", "type": "float", "static": False}],
                "methods": [],
            }
        ]

    def test_added_class_method_includes_parameter_names_and_types(self):
        """カバレッジ補強: パラメータを持つメソッドがJSON出力に正しく含まれること
        (_parameter_to_dict/_method_to_dictが実際に呼ばれる経路)。
        """
        cls = make_class(
            "pkg.Car",
            methods=(
                MethodIR(
                    name="honk",
                    parameters=(ParameterIR(name="times", type="int"),),
                    return_type="None",
                ),
            ),
        )
        diff = SnapshotDiff(classes=ClassDiff(added=(cls,)), relations=RelationDiff())

        payload = json.loads(JsonRenderer().render(diff, meta=META))

        assert payload["classes"]["added"][0]["methods"] == [
            {
                "name": "honk",
                "parameters": [{"name": "times", "type": "int"}],
                "return_type": "None",
            }
        ]

    def test_modified_class_includes_attribute_and_method_diff(self):
        mod = ClassModification(
            fqn="pkg.Car",
            name="Car",
            attributes=AttributeDiff(
                added=(AttributeIR(name="battery", type="Battery"),),
                removed=(AttributeIR(name="wheels", type="List[Wheel]"),),
            ),
            methods=MethodDiff(),
            base_class=make_class("pkg.Car", attributes=(AttributeIR(name="wheels", type="List[Wheel]"),)),
            head_class=make_class("pkg.Car", attributes=(AttributeIR(name="battery", type="Battery"),)),
        )
        diff = SnapshotDiff(classes=ClassDiff(modified=(mod,)), relations=RelationDiff())

        payload = json.loads(JsonRenderer().render(diff, meta=META))

        modified = payload["classes"]["modified"][0]
        assert modified["fqn"] == "pkg.Car"
        assert modified["attributes"]["added"] == [{"name": "battery", "type": "Battery", "static": False}]
        assert modified["attributes"]["removed"] == [
            {"name": "wheels", "type": "List[Wheel]", "static": False}
        ]
        assert modified["attributes"]["changed"] == []


class TestJsonRendererRelations:
    def test_relations_added_and_removed(self):
        added = RelationIR(source_fqn="pkg.Car", target_fqn="pkg.Battery", type=RelationType.COMPOSITION)
        removed = RelationIR(source_fqn="pkg.Vehicle", target_fqn="pkg.Car", type=RelationType.INHERITANCE)
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(added,), removed=(removed,)))

        payload = json.loads(JsonRenderer().render(diff, meta=META))

        assert payload["relations"]["added"] == [
            {"source_fqn": "pkg.Car", "target_fqn": "pkg.Battery", "type": "composition"}
        ]
        assert payload["relations"]["removed"] == [
            {"source_fqn": "pkg.Vehicle", "target_fqn": "pkg.Car", "type": "inheritance"}
        ]
