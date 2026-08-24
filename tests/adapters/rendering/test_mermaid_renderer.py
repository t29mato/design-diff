"""MermaidRenderer のテスト。architecture.md §7 + レビューフィードバック(表示品質)。

合格基準: design-diff自身を解析した図をGitHubのMermaidプレビューに貼り、
スクロールせずに「何が増え、何が消え、何が変わり、どの依存が生えたか」が
一目で分かること。そのために:

- 3状態(追加/削除/変更)を**ASCIIのステータスタグ**(`[+]`/`[-]`/`[~]`)でラベルに前置し、
  かつ**`style <id> fill:...,stroke:...;`文で実際に色も付ける**(追加=緑/削除=赤/変更=黄)。
  Mermaidの`classDef`+`cssClass`によるclassDiagramのスタイリングは、GitHub・mermaid.live
  双方の実機検証で全く反映されないことを確認した(upstream Mermaidの既知の問題。
  https://github.com/mermaid-js/mermaid/issues/1649)。一方、ノード単体を対象にする
  `style`文は別のMermaid機構であり、GitHubの実機(namespace記法・ラベル・メソッド本文と
  併用した状態)で緑/赤/黄が実際に描画されることを確認済み。Mermaid標準構文であり
  GitHub固有の裏技ではないため、GitLab等の他のMermaid実装でも動作する見込み(ただし
  GitHub以外での実機確認はまだ)。ASCIIタグは色だけに頼らないための冗長化として残す
  (色覚特性やカラー非対応ビューアでも状態が読み取れるようにするため)
- 完全修飾名(fqn)をそのままラベルにしない。短い名前 + namespace記法でグループ化
  (fqnはノードIDとしてのみ使い、表示ラベルは短縮する)
- 変更のないクラスは出さない(ノイズ削減)
- 変更クラス数が上限を超えたら、影響度の大きい上位N件だけを図示し、
  残りは診断的な note(純粋なMermaid構文。SVG変換にも耐える)で要約する
"""

from design_diff.adapters.rendering.mermaid_renderer import MermaidRenderer
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


def struck(text: str) -> str:
    """mermaid_rendererの取り消し線合成(U+0336 COMBINING LONG STROKE OVERLAY)
    と同じ変換をテスト側で再現する(削除メンバー行のアサーション用)。
    """
    return "".join(f"{ch}̶" for ch in text)


def make_class(fqn, attributes=(), methods=(), is_abstract=False) -> ClassIR:
    return ClassIR(
        fqn=fqn, name=fqn.rsplit(".", 1)[-1], is_abstract=is_abstract, attributes=attributes, methods=methods
    )


class TestMermaidRendererStructure:
    def test_starts_with_class_diagram_header(self):
        output = MermaidRenderer().render(EMPTY_DIFF)

        assert output.startswith("classDiagram")

    def test_ignores_the_mermaid_kwarg(self):
        """MermaidRenderer自身はRendererPortのmermaid/meta引数を無視してよい(§2)。"""
        output = MermaidRenderer().render(EMPTY_DIFF, mermaid="ignored", meta={"package": "pkg"})
        assert output.startswith("classDiagram")


class TestMermaidRendererLabelsAndNamespaces:
    """レビューフィードバック優先度3: ラベル短縮 + namespace記法によるグループ化。"""

    def test_uses_short_class_name_as_the_visible_label(self):
        added = make_class(
            "shop.domain.models.Product",
            attributes=(AttributeIR(name="price", type="float"),),
        )
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "Product" in output
        assert "shop.domain.models.Product" not in output  # fqnそのままはラベルに出さない

    def test_groups_classes_by_module_path_using_namespace_syntax(self):
        added = make_class("shop.domain.models.Product")
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "namespace shop.domain.models {" in output

    def test_relation_lines_reference_sanitized_ids_not_raw_fqn(self):
        relation = RelationIR(
            source_fqn="shop.domain.models.Car",
            target_fqn="shop.domain.models.Battery",
            type=RelationType.COMPOSITION,
        )
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(relation,)))

        output = MermaidRenderer().render(diff)

        assert "shop_domain_models_Car *-- shop_domain_models_Battery" in output
        # バッククォート付きの生fqnはノードIDとして使わない(可読性のため)
        assert "`shop.domain.models.Car`" not in output

    def test_relation_endpoint_not_in_the_diff_is_declared_as_plain_context_node(self):
        """変更されていないクラスへのリレーションでも、参照先を短いラベルで宣言する。"""
        relation = RelationIR(
            source_fqn="shop.domain.models.Car",
            target_fqn="shop.domain.models.Engine",
            type=RelationType.COMPOSITION,
        )
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(relation,)))

        output = MermaidRenderer().render(diff)

        assert '["Engine"]' in output  # 文脈上の参照のみなのでステータスタグは付かない


class TestMermaidRendererAddedRemoved:
    def test_renders_added_class_with_added_tag(self):
        added = make_class("pkg.models.Battery", attributes=(AttributeIR(name="capacity_kwh", type="float"),))
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert '["[+] Battery"]' in output
        assert "capacity_kwh" in output
        assert "float" in output

    def test_renders_removed_class_with_removed_tag(self):
        removed = make_class("pkg.models.Wheel", attributes=(AttributeIR(name="diameter", type="float"),))
        diff = SnapshotDiff(classes=ClassDiff(removed=(removed,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert '["[-] Wheel"]' in output

    def test_renders_methods_with_parameters_and_return_type(self):
        added = make_class(
            "pkg.models.Car",
            methods=(MethodIR(name="honk", parameters=(), return_type="None"),),
        )
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "honk()" in output
        assert "None" in output


class TestMermaidRendererVisibility:
    """レビューフィードバック(残っている傷1): アンダースコア始まりのメンバーはMermaidの
    可視性マーカー `-`(private)で描く。既定の`+`(public)一色だと、図から
    公開APIが読み取れない。
    """

    def test_public_attribute_uses_plus_marker(self):
        added = make_class("pkg.models.Car", attributes=(AttributeIR(name="engine", type="Engine"),))
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "+engine: Engine" in output

    def test_private_attribute_uses_minus_marker(self):
        added = make_class("pkg.models.Car", attributes=(AttributeIR(name="_engine", type="Engine"),))
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "-_engine: Engine" in output
        assert "+_engine: Engine" not in output

    def test_public_method_uses_plus_marker(self):
        added = make_class(
            "pkg.models.Car", methods=(MethodIR(name="honk", parameters=(), return_type="None"),)
        )
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "+honk()" in output

    def test_private_method_uses_minus_marker(self):
        added = make_class(
            "pkg.models.Car", methods=(MethodIR(name="_helper", parameters=(), return_type="None"),)
        )
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "-_helper()" in output
        assert "+_helper()" not in output


class TestMermaidRendererUntypedMembers:
    """レビューフィードバック(残っている傷2): 型注釈が無い属性が偽の型名`None`として
    表示される問題。型が取れない場合は型部分自体を省略する。
    """

    def test_omits_type_annotation_when_attribute_type_is_none(self):
        added = make_class("pkg.models.Foo", attributes=(AttributeIR(name="payload", type=None),))
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "+payload" in output
        assert "+payload: None" not in output

    def test_keeps_type_annotation_when_attribute_has_a_real_type(self):
        added = make_class("pkg.models.Foo", attributes=(AttributeIR(name="price", type="float"),))
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "+price: float" in output


class TestMermaidRendererModified:
    def test_renders_modified_class_with_modified_style_and_note(self):
        base_car = make_class("pkg.models.Car", attributes=(AttributeIR(name="wheels", type="List[Wheel]"),))
        head_car = make_class("pkg.models.Car", attributes=(AttributeIR(name="battery", type="Battery"),))
        mod = ClassModification(
            fqn="pkg.models.Car",
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

        assert '["[~] Car"]' in output
        assert "battery" in output  # head時点の属性を表示
        assert "note for pkg_models_Car" in output
        assert "+ battery" in output  # noteの中に差分サマリ
        assert "- wheels" in output


class TestMermaidRendererMemberLevelDiff:
    """HQ #36の品質判定(差し戻し): メンバー単位の増減が図の中で**視覚的に一目で
    分かること**が合格基準。従来のASCIIサフィックスタグ(`[+]`等)は情報としては
    存在するが視覚的な顕著性が足りないという指摘を受け、メンバー行の**先頭**に
    絵文字マーカー(➕追加/➖削除/🔀変更)を付ける形に変更した。Mermaidの
    classDiagramはメンバー行単位のstyle(色)を持たないため(公式ドキュメントで
    確認済み。architecture.md §7参照)、色ではなく絵文字グリフで表現する。
    """

    def test_added_attribute_gets_a_plus_emoji_prefix(self):
        base = make_class("pkg.models.Car")
        head = make_class("pkg.models.Car", attributes=(AttributeIR(name="battery", type="Battery"),))
        mod = ClassModification(
            fqn="pkg.models.Car",
            name="Car",
            attributes=AttributeDiff(added=(AttributeIR(name="battery", type="Battery"),)),
            methods=MethodDiff(),
            base_class=base,
            head_class=head,
        )
        diff = SnapshotDiff(classes=ClassDiff(modified=(mod,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "➕ +battery: Battery" in output

    def test_removed_attribute_is_shown_in_the_class_body_with_a_minus_emoji(self):
        """headにはもう存在しない属性でも、クラス本体の中に➖付き・取り消し線
        付きで表示する(これまではnoteだけにしか出ておらず、本体を見ただけでは
        分からなかった)。取り消し線はUnicode合成文字(U+0336)で、GitHub実機
        検証(スパイク)で崩れずに描画されることを確認済み(architecture.md §7)。
        """
        base = make_class("pkg.models.Car", attributes=(AttributeIR(name="wheels", type="List[Wheel]"),))
        head = make_class("pkg.models.Car")
        mod = ClassModification(
            fqn="pkg.models.Car",
            name="Car",
            attributes=AttributeDiff(removed=(AttributeIR(name="wheels", type="List[Wheel]"),)),
            methods=MethodDiff(),
            base_class=base,
            head_class=head,
        )
        diff = SnapshotDiff(classes=ClassDiff(modified=(mod,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert f"➖ {struck('+wheels: List[Wheel]')}" in output

    def test_changed_attribute_type_gets_a_shuffle_emoji_with_the_old_type(self):
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

        output = MermaidRenderer().render(diff)

        assert "🔀 +wheels: List[Wheel] (was: int)" in output

    def test_unchanged_attribute_has_no_diff_emoji(self):
        unchanged = AttributeIR(name="name", type="str")
        base = make_class("pkg.models.Car", attributes=(unchanged, AttributeIR(name="wheels", type="int")))
        head = make_class("pkg.models.Car", attributes=(unchanged,))
        mod = ClassModification(
            fqn="pkg.models.Car",
            name="Car",
            attributes=AttributeDiff(removed=(AttributeIR(name="wheels", type="int"),)),
            methods=MethodDiff(),
            base_class=base,
            head_class=head,
        )
        diff = SnapshotDiff(classes=ClassDiff(modified=(mod,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        line = next(line for line in output.splitlines() if "+name: str" in line)
        assert not any(e in line for e in ("➕", "➖", "🔀"))  # 未変更メンバーにはマーカーを付けない

    def test_added_method_gets_a_plus_emoji_prefix(self):
        base = make_class("pkg.models.Car")
        head = make_class(
            "pkg.models.Car", methods=(MethodIR(name="honk", parameters=(), return_type="None"),)
        )
        mod = ClassModification(
            fqn="pkg.models.Car",
            name="Car",
            attributes=AttributeDiff(),
            methods=MethodDiff(added=(MethodIR(name="honk", parameters=(), return_type="None"),)),
            base_class=base,
            head_class=head,
        )
        diff = SnapshotDiff(classes=ClassDiff(modified=(mod,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "➕ +honk(): None" in output

    def test_removed_method_is_shown_in_the_class_body_with_a_minus_emoji(self):
        base = make_class(
            "pkg.models.Car", methods=(MethodIR(name="honk", parameters=(), return_type="None"),)
        )
        head = make_class("pkg.models.Car")
        mod = ClassModification(
            fqn="pkg.models.Car",
            name="Car",
            attributes=AttributeDiff(),
            methods=MethodDiff(removed=(MethodIR(name="honk", parameters=(), return_type="None"),)),
            base_class=base,
            head_class=head,
        )
        diff = SnapshotDiff(classes=ClassDiff(modified=(mod,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert f"➖ {struck('+honk(): None')}" in output

    def test_changed_method_gets_a_shuffle_emoji(self):
        old_method = MethodIR(name="apply_discount", parameters=(), return_type="float")
        new_method = MethodIR(
            name="apply_discount",
            parameters=(ParameterIR(name="code", type="str"),),
            return_type="float",
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

        output = MermaidRenderer().render(diff)

        assert "🔀 +apply_discount(code: str): float" in output


class TestMermaidRendererColorStyling:
    """`style <id> fill:...,stroke:...;` によるノード単位の色付け。

    classDef/cssClassはGitHub・mermaid.live双方で反映されないことを確認済みだが、
    `style`文は別機構であり、GitHub実機(namespace併用時も含む)で実際に緑/赤/黄が
    描画されることを確認済み。architecture.md §7参照。
    """

    def test_added_class_gets_a_green_style_line(self):
        added = make_class("pkg.models.Battery")
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "style pkg_models_Battery fill:#e6ffed,stroke:#22863a" in output

    def test_removed_class_gets_a_red_style_line(self):
        removed = make_class("pkg.models.Wheel")
        diff = SnapshotDiff(classes=ClassDiff(removed=(removed,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "style pkg_models_Wheel fill:#ffeef0,stroke:#b31d28" in output

    def test_style_line_also_sets_text_color_not_just_background(self):
        """レビューフィードバック: fill/strokeだけでは、GitHub実機でタイトル・メンバー
        文字がテーマ既定の薄いグレーのまま残り、色分けの効果が半減する。`color`も
        指定し、文字自体も状態色になるようにする。
        """
        added = make_class("pkg.models.Battery")
        diff = SnapshotDiff(classes=ClassDiff(added=(added,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        style_line = next(line for line in output.splitlines() if "style pkg_models_Battery" in line)
        assert "color:#22863a" in style_line

    def test_modified_class_gets_a_yellow_style_line(self):
        base_car = make_class("pkg.models.Car")
        head_car = make_class("pkg.models.Car")
        mod = ClassModification(
            fqn="pkg.models.Car",
            name="Car",
            attributes=AttributeDiff(),
            methods=MethodDiff(),
            base_class=base_car,
            head_class=head_car,
        )
        diff = SnapshotDiff(classes=ClassDiff(modified=(mod,)), relations=RelationDiff())

        output = MermaidRenderer().render(diff)

        assert "style pkg_models_Car fill:#fff8e6,stroke:#b08800" in output

    def test_context_only_relation_endpoint_gets_no_style_line(self):
        """変更されていない、文脈上の参照のみのクラスには色を付けない(styleなし=None)。"""
        relation = RelationIR(
            source_fqn="pkg.models.Car",
            target_fqn="pkg.models.Engine",
            type=RelationType.COMPOSITION,
        )
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(relation,)))

        output = MermaidRenderer().render(diff)

        assert "style pkg_models_Engine" not in output


class TestMermaidRendererUnchanged:
    def test_unchanged_classes_are_not_part_of_the_diff_and_produce_no_extra_class_block(self):
        output = MermaidRenderer().render(EMPTY_DIFF)
        assert '["' not in output


class TestMermaidRendererRelations:
    def test_renders_added_composition(self):
        relation = RelationIR(
            source_fqn="pkg.models.Car",
            target_fqn="pkg.models.Battery",
            type=RelationType.COMPOSITION,
        )
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(relation,)))

        output = MermaidRenderer().render(diff)

        assert "pkg_models_Car *-- pkg_models_Battery" in output

    def test_renders_added_inheritance(self):
        relation = RelationIR(
            source_fqn="pkg.models.Vehicle",
            target_fqn="pkg.models.Car",
            type=RelationType.INHERITANCE,
        )
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(relation,)))

        output = MermaidRenderer().render(diff)

        assert "pkg_models_Vehicle <|-- pkg_models_Car" in output

    def test_marks_removed_relations_distinctly_from_added(self):
        added = RelationIR(
            source_fqn="pkg.models.Car",
            target_fqn="pkg.models.Battery",
            type=RelationType.COMPOSITION,
        )
        removed = RelationIR(
            source_fqn="pkg.models.Car",
            target_fqn="pkg.models.Wheel",
            type=RelationType.COMPOSITION,
        )
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(added,), removed=(removed,)))

        output = MermaidRenderer().render(diff)

        added_line = next(line for line in output.splitlines() if "Battery" in line and "*--" in line)
        removed_line = next(line for line in output.splitlines() if "Wheel" in line and "*--" in line)
        assert added_line != removed_line
        assert "removed" in removed_line

    def test_added_relation_gets_a_new_label(self):
        """HQ指摘(デモ図との品質比較): 追加されたリレーションにMermaidの矢印
        ラベル記法(`A --> B : label`)で"new"ラベルを付ける。
        """
        relation = RelationIR(
            source_fqn="pkg.models.Car",
            target_fqn="pkg.models.Battery",
            type=RelationType.COMPOSITION,
        )
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(relation,)))

        output = MermaidRenderer().render(diff)

        assert "pkg_models_Car *-- pkg_models_Battery : new" in output

    def test_removed_relation_gets_a_removed_label(self):
        """HQ指摘: 削除されたリレーションには同じ記法で"removed"ラベルを付ける。"""
        relation = RelationIR(
            source_fqn="pkg.models.Car",
            target_fqn="pkg.models.Wheel",
            type=RelationType.COMPOSITION,
        )
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(removed=(relation,)))

        output = MermaidRenderer().render(diff)

        assert "pkg_models_Car *-- pkg_models_Wheel : removed" in output

    def test_inheritance_relation_also_gets_a_label(self):
        relation = RelationIR(
            source_fqn="pkg.models.Vehicle",
            target_fqn="pkg.models.Car",
            type=RelationType.INHERITANCE,
        )
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(added=(relation,)))

        output = MermaidRenderer().render(diff)

        assert "pkg_models_Vehicle <|-- pkg_models_Car : new" in output


class TestMermaidRendererWarnings:
    """発見した問題(サブモジュールのimport失敗が無言でスキップされる)への対応。
    HQ指摘: 沈黙原則が『沈黙=変更なし』に依存している以上、部分解析だった事実
    (SnapshotDiff.warnings)は図の中にも見える形で出す必要がある。
    """

    def test_no_warnings_note_when_warnings_is_empty(self):
        output = MermaidRenderer().render(EMPTY_DIFF)
        assert "解析できなかった" not in output

    def test_warnings_note_lists_skipped_module_count_and_names(self):
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(), warnings=("pkg.broken",))

        output = MermaidRenderer().render(diff)

        assert 'note "' in output
        assert "解析できなかったモジュール" in output
        assert "1件" in output
        assert "pkg.broken" in output

    def test_warnings_note_lists_every_skipped_module(self):
        diff = SnapshotDiff(
            classes=ClassDiff(),
            relations=RelationDiff(),
            warnings=("pkg.a_broken", "pkg.b_broken"),
        )

        output = MermaidRenderer().render(diff)

        assert "2件" in output
        assert "pkg.a_broken" in output
        assert "pkg.b_broken" in output

    def test_warnings_note_appears_even_when_there_are_no_class_changes(self):
        """『変更なしに見えるが解析は部分的』の場合でも、有効なMermaidが出ること。"""
        diff = SnapshotDiff(classes=ClassDiff(), relations=RelationDiff(), warnings=("pkg.broken",))

        output = MermaidRenderer().render(diff)

        assert output.startswith("classDiagram")
        assert "pkg.broken" in output


class TestMermaidRendererSizeCap:
    """追加要件: 図のサイズ制御。変更クラス数が上限を超えたら上位N件のみ図示。"""

    def _make_many_added_classes(self, count: int) -> tuple[ClassIR, ...]:
        return tuple(
            make_class(f"pkg.models.Class{i}", attributes=(AttributeIR(name="x", type="int"),))
            for i in range(count)
        )

    def test_renders_all_classes_when_under_the_cap(self):
        added = self._make_many_added_classes(5)
        diff = SnapshotDiff(classes=ClassDiff(added=added), relations=RelationDiff())

        output = MermaidRenderer(max_classes=20).render(diff)

        for cls in added:
            assert f'["[+] {cls.name}"]' in output

    def test_caps_the_number_of_rendered_classes_when_over_the_limit(self):
        added = self._make_many_added_classes(25)
        diff = SnapshotDiff(classes=ClassDiff(added=added), relations=RelationDiff())

        output = MermaidRenderer(max_classes=20).render(diff)

        rendered_count = sum(1 for cls in added if f'["[+] {cls.name}"]' in output)
        assert rendered_count == 20

    def test_adds_a_summary_note_when_capped(self):
        added = self._make_many_added_classes(25)
        diff = SnapshotDiff(classes=ClassDiff(added=added), relations=RelationDiff())

        output = MermaidRenderer(max_classes=20).render(diff)

        assert 'note "' in output
        assert "25" in output  # 変更クラス総数への言及
        assert "20" in output  # 表示件数への言及

    def test_prioritizes_classes_with_larger_diffs_when_capped(self):
        small = make_class("pkg.models.Small", attributes=(AttributeIR(name="a", type="int"),))
        big = make_class(
            "pkg.models.Big",
            attributes=tuple(AttributeIR(name=f"f{i}", type="int") for i in range(10)),
        )
        filler = self._make_many_added_classes(20)
        diff = SnapshotDiff(classes=ClassDiff(added=(small, big, *filler)), relations=RelationDiff())

        output = MermaidRenderer(max_classes=1).render(diff)

        assert '["[+] Big"]' in output
        assert '["[+] Small"]' not in output

    def test_output_remains_valid_standalone_mermaid_text_when_capped(self):
        """要約は`note "..."` というMermaid標準構文で表現し、Markdown表などは混ぜない
        (GitHubプレビューだけでなくSVG変換パイプラインにもそのまま渡せるようにするため)。
        """
        added = self._make_many_added_classes(25)
        diff = SnapshotDiff(classes=ClassDiff(added=added), relations=RelationDiff())

        output = MermaidRenderer(max_classes=20).render(diff)

        assert "|" not in output.split("note")[0]  # Markdownテーブルの罫線が混じっていない
        for line in output.splitlines():
            assert not line.strip().startswith("#")  # Markdown見出しが混じっていない
