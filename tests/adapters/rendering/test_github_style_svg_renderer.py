"""GitHubStyleSvgRenderer のテスト。

HQ #36/#38(オーナー再差し戻し)への対応: Mermaidはメンバー単位のスタイリングを
一切サポートしないため(architecture.md §7.1)、design-diff自身が直接SVGを生成する
ネイティブレンダラーを実装した。ビジュアル仕様(GitHub diff風)はHQ(Fable)が指定。
"""

from design_diff.adapters.rendering.github_style_svg_renderer import GitHubStyleSvgRenderer
from design_diff.domain.diff import (
    AttributeChange,
    AttributeDiff,
    ClassDiff,
    ClassModification,
    MethodChange,
    MethodDiff,
    RelationDiff,
    SnapshotDiff,
)
from design_diff.domain.model import AttributeIR, ClassIR, MethodIR, ParameterIR, RelationIR, RelationType

EMPTY_DIFF = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff())


def make_class(fqn, attributes=(), methods=()) -> ClassIR:
    return ClassIR(fqn=fqn, name=fqn.rsplit(".", 1)[-1], attributes=attributes, methods=methods)


class TestGitHubStyleSvgRendererStructure:
    def test_produces_a_self_contained_svg_document(self):
        output = GitHubStyleSvgRenderer().render(EMPTY_DIFF)

        assert output.startswith("<svg")
        assert output.endswith("</svg>")
        assert 'xmlns="http://www.w3.org/2000/svg"' in output

    def test_is_self_contained_no_external_resource_references(self):
        """外部フォント・画像参照が無いこと(GitHub PRコメントへの埋め込みを想定)。"""
        output = GitHubStyleSvgRenderer().render(EMPTY_DIFF)

        assert "http://" not in output.replace("http://www.w3.org/2000/svg", "")
        assert "https://" not in output
        assert "<image" not in output
        assert "xlink:href" not in output

    def test_ignores_mermaid_and_meta_kwargs(self):
        output = GitHubStyleSvgRenderer().render(EMPTY_DIFF, mermaid="classDiagram", meta={"package": "pkg"})

        assert "classDiagram" not in output


class TestGitHubStyleSvgRendererAddedRemoved:
    def test_added_class_gets_a_green_header_and_plus_prefixed_label(self):
        cls = make_class("pkg.models.Battery", attributes=(AttributeIR(name="capacity", type="float"),))
        diff = SnapshotDiff(classes=ClassDiff(added=(cls,)), relations=RelationDiff())

        output = GitHubStyleSvgRenderer().render(diff)

        assert "#d1f8d9" in output  # 追加クラスのヘッダー色
        assert "[+] Battery" in output
        assert ">+capacity: float<" in output

    def test_removed_class_gets_a_red_header_and_strikethrough_label(self):
        cls = make_class("pkg.models.LegacyThing", attributes=(AttributeIR(name="text", type="str"),))
        diff = SnapshotDiff(classes=ClassDiff(removed=(cls,)), relations=RelationDiff())

        output = GitHubStyleSvgRenderer().render(diff)

        assert "#ffd7d5" in output  # 削除クラスのヘッダー色
        assert "[-] LegacyThing" in output
        assert 'text-decoration="line-through"' in output

    def test_added_class_member_line_has_plus_gutter_and_green_background(self):
        cls = make_class("pkg.models.Battery", attributes=(AttributeIR(name="capacity", type="float"),))
        diff = SnapshotDiff(classes=ClassDiff(added=(cls,)), relations=RelationDiff())

        output = GitHubStyleSvgRenderer().render(diff)

        assert "#e6ffec" in output  # 追加行の背景(GitHub diff配色)
        assert ">+<" in output  # ガター記号


class TestGitHubStyleSvgRendererModified:
    def test_modified_class_shows_added_removed_changed_and_unchanged_lines(self):
        base = make_class(
            "pkg.models.Cart",
            attributes=(AttributeIR(name="legacy_notes", type="str"), AttributeIR(name="items", type="List")),
        )
        head = make_class(
            "pkg.models.Cart",
            attributes=(
                AttributeIR(name="items", type="List"),
                AttributeIR(name="discount_code", type="Optional[DiscountCode]"),
            ),
        )
        mod = ClassModification(
            fqn="pkg.models.Cart",
            name="Cart",
            attributes=AttributeDiff(
                added=(AttributeIR(name="discount_code", type="Optional[DiscountCode]"),),
                removed=(AttributeIR(name="legacy_notes", type="str"),),
            ),
            methods=MethodDiff(),
            base_class=base,
            head_class=head,
        )
        diff = SnapshotDiff(classes=ClassDiff(modified=(mod,)), relations=RelationDiff())

        output = GitHubStyleSvgRenderer().render(diff)

        assert "#d4a72c" in output  # 変更クラスの枠色
        assert "[~] Cart" in output
        assert ">+discount_code: Optional[DiscountCode]<" in output  # 追加行
        assert "#e6ffec" in output  # 追加行の背景
        assert "#ffebe9" in output  # 削除行の背景
        assert "#57606a" in output  # 無変更行のガター色(記号は空)

    def test_changed_attribute_shows_old_arrow_new_on_one_line(self):
        base = make_class("pkg.models.Car", attributes=(AttributeIR(name="wheels", type="int"),))
        head = make_class("pkg.models.Car", attributes=(AttributeIR(name="wheels", type="List[Wheel]"),))
        mod = ClassModification(
            fqn="pkg.models.Car",
            name="Car",
            attributes=AttributeDiff(
                changed=(
                    AttributeChange(
                        name="wheels",
                        old_type="int",
                        new_type="List[Wheel]",
                        old_static=False,
                        new_static=False,
                    ),
                )
            ),
            methods=MethodDiff(),
            base_class=base,
            head_class=head,
        )
        diff = SnapshotDiff(classes=ClassDiff(modified=(mod,)), relations=RelationDiff())

        output = GitHubStyleSvgRenderer().render(diff)

        assert "#fff8c5" in output  # 変更行の背景
        assert "+wheels: int → +wheels: List[Wheel]" in output

    def test_changed_method_shows_old_arrow_new_on_one_line(self):
        old_method = MethodIR(name="apply_discount", parameters=(), return_type="float")
        new_method = MethodIR(
            name="apply_discount", parameters=(ParameterIR(name="code", type="str"),), return_type="float"
        )
        base = make_class("pkg.models.Product", methods=(old_method,))
        head = make_class("pkg.models.Product", methods=(new_method,))
        mod = ClassModification(
            fqn="pkg.models.Product",
            name="Product",
            attributes=AttributeDiff(),
            methods=MethodDiff(
                changed=(MethodChange(name="apply_discount", old=old_method, new=new_method),)
            ),
            base_class=base,
            head_class=head,
        )
        diff = SnapshotDiff(classes=ClassDiff(modified=(mod,)), relations=RelationDiff())

        output = GitHubStyleSvgRenderer().render(diff)

        assert "+apply_discount(): float → +apply_discount(code: str): float" in output


class TestGitHubStyleSvgRendererRelations:
    def test_added_inheritance_gets_a_green_marker_and_new_label(self):
        relation = RelationIR(
            source_fqn="pkg.models.Car", target_fqn="pkg.models.Vehicle", type=RelationType.INHERITANCE
        )
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(relation,)))

        output = GitHubStyleSvgRenderer().render(diff)

        assert "arrow-inherit-added" in output
        assert ">new<" in output

    def test_removed_composition_gets_a_red_dashed_marker_and_removed_label(self):
        relation = RelationIR(
            source_fqn="pkg.models.Car", target_fqn="pkg.models.Wheel", type=RelationType.COMPOSITION
        )
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(removed=(relation,)))

        output = GitHubStyleSvgRenderer().render(diff)

        assert "diamond-compose-removed" in output
        assert "stroke-dasharray" in output
        assert ">removed<" in output

    def test_relation_endpoint_not_in_the_diff_is_declared_as_a_context_box(self):
        relation = RelationIR(
            source_fqn="pkg.models.Car", target_fqn="pkg.models.Battery", type=RelationType.COMPOSITION
        )
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(relation,)))

        output = GitHubStyleSvgRenderer().render(diff)

        assert "Car" in output
        assert "Battery" in output


class TestGitHubStyleSvgRendererNamespaces:
    def test_namespace_label_is_rendered(self):
        cls = make_class("pkg.models.Battery", attributes=(AttributeIR(name="x", type="int"),))
        diff = SnapshotDiff(classes=ClassDiff(added=(cls,)), relations=RelationDiff())

        output = GitHubStyleSvgRenderer().render(diff)

        assert ">pkg.models<" in output


class TestGitHubStyleSvgRendererWarnings:
    """発見した問題(2026-08-29の「自己説明的か点検」): PRコメントに実際に埋め込まれる
    画像(--format svgの既定)には`diff.warnings`が表示されておらず、Mermaidの
    `<details>`フォールバックを開かない限りレビュアーが部分解析に気付けなかった。
    沈黙原則(§4.1, §7.1)を毒す抜け穴だったため、SVG本体にも警告バナーを追加した。
    """

    def test_no_warnings_banner_when_warnings_is_empty(self):
        output = GitHubStyleSvgRenderer().render(EMPTY_DIFF)
        assert "could not be analyzed" not in output

    def test_warnings_banner_lists_skipped_module_count_and_names(self):
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(), warnings=("pkg.broken",))

        output = GitHubStyleSvgRenderer().render(diff)

        assert "1 module(s) could not be analyzed" in output
        assert "pkg.broken" in output

    def test_warnings_banner_lists_every_skipped_module(self):
        diff = SnapshotDiff(
            classes=ClassDiff(), relations=RelationDiff(), warnings=("pkg.a_broken", "pkg.b_broken")
        )

        output = GitHubStyleSvgRenderer().render(diff)

        assert "2 module(s) could not be analyzed" in output
        assert "pkg.a_broken" in output
        assert "pkg.b_broken" in output

    def test_warnings_banner_appears_even_when_there_are_no_class_changes(self):
        """『変更なしに見えるが解析は部分的』の場合でも、有効なSVGが出ること。"""
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(), warnings=("pkg.broken",))

        output = GitHubStyleSvgRenderer().render(diff)

        assert output.startswith("<svg")
        assert output.endswith("</svg>")
        assert "pkg.broken" in output

    def test_class_boxes_are_shifted_below_the_warnings_banner(self):
        """バナーの分だけ既存コンテンツが下にずれ、重ならないこと。"""
        cls = make_class("pkg.models.Battery", attributes=(AttributeIR(name="x", type="int"),))
        diff_without_warnings = SnapshotDiff(classes=ClassDiff(added=(cls,)), relations=RelationDiff())
        diff_with_warnings = SnapshotDiff(
            classes=ClassDiff(added=(cls,)), relations=RelationDiff(), warnings=("pkg.broken",)
        )

        without = GitHubStyleSvgRenderer().render(diff_without_warnings)
        with_warnings = GitHubStyleSvgRenderer().render(diff_with_warnings)

        def svg_height(svg: str) -> int:
            import re

            return int(re.search(r'height="(\d+)"', svg).group(1))

        assert svg_height(with_warnings) > svg_height(without)
        assert '<g transform="translate(0,' in with_warnings


class TestGitHubStyleSvgRendererEscaping:
    def test_special_characters_in_type_names_are_escaped(self):
        """未解決の型名などに"<"/">"/"&"が紛れ込んでもSVG構文が壊れないこと。"""
        cls = make_class("pkg.models.Widget", attributes=(AttributeIR(name="handler", type="A<B>&C"),))
        diff = SnapshotDiff(classes=ClassDiff(added=(cls,)), relations=RelationDiff())

        output = GitHubStyleSvgRenderer().render(diff)

        assert "A<B>&C" not in output
        assert "A&lt;B&gt;&amp;C" in output
