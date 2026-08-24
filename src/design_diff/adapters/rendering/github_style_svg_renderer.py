"""GitHubStyleSvgRenderer。RendererPortの実装。

HQ #36/#38でオーナーからの再差し戻し(2026-08-25): 「絵文字を使うのではなく、
GitHub diffみたいに視覚的にわかる形に。Mermaidやplantumlで限界があるなら
他の方法を考えて」。Mermaid classDiagramはメンバー単位のスタイリングを一切
サポートしない(公式ドキュメント・GitHub issueで確認済み。
architecture.md §7.1)ため、Mermaidへの依存をやめ、design-diff自身が直接SVGを
生成するネイティブレンダラーを実装した。

ビジュアル仕様はHQ(Fable)が指定(詳細はarchitecture.md §7.2):
- クラスボックス: 角丸4px、ヘッダー帯(クラス名+状態)。追加=緑ヘッダー、
  削除=赤ヘッダー+クラス名取り消し線、変更=ヘッダー中立+黄枠
- メンバー行はGitHub diffの行そのもの: 左ガター(+/-/±)+行全体の背景色。
  変更行は「旧の型 → 新の型」を1行で示す
- リレーション: 実線+三角(継承)/菱形(コンポジション)。追加=緑+`new`ラベル、
  削除=赤破線+`removed`ラベル
- レイアウトは単純なグリッド(名前空間ごとに行を折り返す)。はみ出すより
  縦に伸びる方を優先する
- 自己完結SVG(外部フォント・画像参照なし。フォント名の指定のみで、URLでの
  フォント取得は行わない)

mermaid-cli経由の`--format svg-mermaid`(旧実装、`MermaidCliSvgRenderer`)とは
独立したモジュール(adapters.rendering内での相互参照は import-linter の
`adapters-independence`契約の対象外。同一パッケージ内のため)。
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

from design_diff.domain.diff import AttributeChange, ClassModification, SnapshotDiff
from design_diff.domain.model import AttributeIR, ClassIR, MethodIR, RelationIR, RelationType

_FQN_SEPARATOR = "."

# -- ビジュアル定数(HQ指定の配色・寸法) --------------------------------------

_CHAR_WIDTH = 7.4  # monospace 12-13px相当の概算文字幅(グリッド配置なので概算で十分)
_LINE_HEIGHT = 18
_HEADER_HEIGHT = 26
_PADDING = 8
_GUTTER_WIDTH = 20  # 「幅1.2em」相当のガター
_MIN_BOX_WIDTH = 170
_NAMESPACE_PADDING = 16
_NAMESPACE_LABEL_HEIGHT = 20
_MAX_ROW_WIDTH = 900  # これを超えたら次の行へ折り返す(横より縦に伸ばす)
_BOX_GAP_X = 28
_BOX_GAP_Y = 28
_NAMESPACE_GAP_Y = 36
_MARGIN = 16
_FONT_STACK = "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"

_HEADER_FILL = {"added": "#d1f8d9", "removed": "#ffd7d5", "modified": "#f6f8fa", None: "#f6f8fa"}
_BORDER_COLOR = {"added": "#1a7f37", "removed": "#cf222e", "modified": "#d4a72c", None: "#d0d7de"}
_BORDER_WIDTH = {"added": 1.5, "removed": 1.5, "modified": 2.0, None: 1.0}
_STATUS_PREFIX = {"added": "[+] ", "removed": "[-] ", "modified": "[~] ", None: ""}

_LINE_BG = {"added": "#e6ffec", "removed": "#ffebe9", "changed": "#fff8c5", "unchanged": None}
_GUTTER_SYMBOL = {"added": "+", "removed": "-", "changed": "±", "unchanged": ""}
_GUTTER_COLOR = {"added": "#1a7f37", "removed": "#cf222e", "changed": "#9a6700", "unchanged": "#57606a"}

_RELATION_COLOR = {True: "#1a7f37", False: "#cf222e"}
_RELATION_LABEL = {True: "new", False: "removed"}


def _escape(text: str) -> str:
    return html.escape(text, quote=True)


def _namespace(fqn: str) -> str | None:
    if _FQN_SEPARATOR not in fqn:
        return None
    return fqn.rsplit(_FQN_SEPARATOR, 1)[0]


def _short_label(fqn: str) -> str:
    return fqn.rsplit(_FQN_SEPARATOR, 1)[-1]


# -- メンバー行のテキスト化(GitHub diff風の1行) ------------------------------


def _attr_text(attr: AttributeIR) -> str:
    marker = "-" if attr.name.startswith("_") else "+"
    if attr.type is None:
        return f"{marker}{attr.name}"
    return f"{marker}{attr.name}: {attr.type}"


def _attr_text_with_type(name: str, type_: str | None) -> str:
    marker = "-" if name.startswith("_") else "+"
    if type_ is None:
        return f"{marker}{name}"
    return f"{marker}{name}: {type_}"


def _method_text(method: MethodIR) -> str:
    marker = "-" if method.name.startswith("_") else "+"
    params = ", ".join(f"{p.name}: {p.type}" if p.type else p.name for p in method.parameters)
    text = f"{marker}{method.name}({params})"
    if method.return_type:
        text += f": {method.return_type}"
    return text


@dataclass
class _MemberLine:
    text: str
    status: str  # "added" / "removed" / "changed" / "unchanged"


def _whole_class_lines(cls: ClassIR, status: str) -> list[_MemberLine]:
    lines = [_MemberLine(_attr_text(a), status) for a in cls.attributes]
    lines += [_MemberLine(_method_text(m), status) for m in cls.methods]
    return lines


def _attribute_change_line(name: str, change: AttributeChange) -> _MemberLine:
    old_text = _attr_text_with_type(name, change.old_type)
    new_text = _attr_text_with_type(name, change.new_type)
    return _MemberLine(f"{old_text} → {new_text}", "changed")


def _method_change_line(new_method: MethodIR, old_method: MethodIR) -> _MemberLine:
    return _MemberLine(f"{_method_text(old_method)} → {_method_text(new_method)}", "changed")


def _modified_class_lines(mod: ClassModification) -> list[_MemberLine]:
    """GitHub diff風の1クラス分の行を組み立てる(変更行は「旧 → 新」を1行で示す)。"""
    added_attrs = {a.name for a in mod.attributes.added}
    changed_attrs = {c.name: c for c in mod.attributes.changed}
    lines: list[_MemberLine] = []
    for attribute in mod.head_class.attributes:
        if attribute.name in added_attrs:
            lines.append(_MemberLine(_attr_text(attribute), "added"))
        elif attribute.name in changed_attrs:
            lines.append(_attribute_change_line(attribute.name, changed_attrs[attribute.name]))
        else:
            lines.append(_MemberLine(_attr_text(attribute), "unchanged"))
    for removed_attr in mod.attributes.removed:
        lines.append(_MemberLine(_attr_text(removed_attr), "removed"))

    added_methods = {m.name for m in mod.methods.added}
    changed_methods = {c.name: c for c in mod.methods.changed}
    for method in mod.head_class.methods:
        if method.name in added_methods:
            lines.append(_MemberLine(_method_text(method), "added"))
        elif method.name in changed_methods:
            lines.append(_method_change_line(method, changed_methods[method.name].old))
        else:
            lines.append(_MemberLine(_method_text(method), "unchanged"))
    for removed_method in mod.methods.removed:
        lines.append(_MemberLine(_method_text(removed_method), "removed"))
    return lines


# -- ジオメトリ ---------------------------------------------------------------


@dataclass
class _ClassBox:
    fqn: str
    label: str
    namespace: str | None
    status: str | None  # "added"/"removed"/"modified"/None(文脈上の参照のみ)
    lines: list[_MemberLine] = field(default_factory=list)
    x: float = 0.0
    y: float = 0.0
    width: float = 0.0
    height: float = 0.0


def _collect_boxes(diff: SnapshotDiff) -> dict[str, _ClassBox]:
    boxes: dict[str, _ClassBox] = {}
    for cls in diff.classes.added:
        boxes[cls.fqn] = _ClassBox(
            fqn=cls.fqn, label=_short_label(cls.fqn), namespace=_namespace(cls.fqn),
            status="added", lines=_whole_class_lines(cls, "added"),
        )
    for cls in diff.classes.removed:
        boxes[cls.fqn] = _ClassBox(
            fqn=cls.fqn, label=_short_label(cls.fqn), namespace=_namespace(cls.fqn),
            status="removed", lines=_whole_class_lines(cls, "removed"),
        )
    for mod in diff.classes.modified:
        boxes[mod.fqn] = _ClassBox(
            fqn=mod.fqn, label=_short_label(mod.fqn), namespace=_namespace(mod.fqn),
            status="modified", lines=_modified_class_lines(mod),
        )
    # リレーションの参照先が非変更クラスの場合、文脈として装飾なしのボックスを宣言する
    # (Mermaidレンダラーと同じ考え方。architecture.md §7)。
    for relation in (*diff.relations.added, *diff.relations.removed):
        for fqn in (relation.source_fqn, relation.target_fqn):
            if fqn not in boxes:
                boxes[fqn] = _ClassBox(
                    fqn=fqn, label=_short_label(fqn), namespace=_namespace(fqn), status=None
                )
    return boxes


def _measure(box: _ClassBox) -> None:
    header_chars = len(_STATUS_PREFIX[box.status]) + len(box.label)
    content_chars = [len(line.text) for line in box.lines]
    max_chars = max([header_chars, *content_chars]) if content_chars else header_chars
    box.width = max(_MIN_BOX_WIDTH, _GUTTER_WIDTH + max_chars * _CHAR_WIDTH + 2 * _PADDING)
    body_height = len(box.lines) * _LINE_HEIGHT
    box.height = _HEADER_HEIGHT + body_height + (_PADDING if box.lines else 0)


_LayoutResult = tuple[float, float, list[tuple[str | None, float, float, float, float]]]


def _layout(boxes: dict[str, _ClassBox]) -> _LayoutResult:
    """名前空間ごとにクラスをグリッド配置し、(全体幅, 全体高さ, 名前空間帯一覧)を返す。

    HQ指定: 「単純なグリッド配置でよい。凝ったレイアウトエンジンは不要。はみ出すより
    縦に伸びる方を選ぶ」。行の最大幅(_MAX_ROW_WIDTH)を超えたら次の行へ折り返す
    単純なフロー配置とし、名前空間ごとの帯を縦に積む。
    """
    for box in boxes.values():
        _measure(box)

    by_namespace: dict[str | None, list[_ClassBox]] = {}
    for box in boxes.values():
        by_namespace.setdefault(box.namespace, []).append(box)

    ordered_namespaces = sorted(ns for ns in by_namespace if ns is not None)
    if None in by_namespace:
        ordered_namespaces.append(None)

    cursor_y = _MARGIN
    max_right = 0.0
    namespace_bands: list[tuple[str | None, float, float, float, float]] = []

    for namespace in ordered_namespaces:
        group = sorted(by_namespace[namespace], key=lambda b: b.fqn)
        band_top = cursor_y
        label_offset = _NAMESPACE_LABEL_HEIGHT if namespace else 0
        row_start_x = _MARGIN + _NAMESPACE_PADDING
        row_x = row_start_x
        row_y = band_top + label_offset + _NAMESPACE_PADDING
        row_height = 0.0
        band_right = row_x
        for box in group:
            if row_x != row_start_x and row_x + box.width > _MAX_ROW_WIDTH:
                row_y += row_height + _BOX_GAP_Y
                row_x = row_start_x
                row_height = 0.0
            box.x = row_x
            box.y = row_y
            row_x += box.width + _BOX_GAP_X
            row_height = max(row_height, box.height)
            band_right = max(band_right, row_x - _BOX_GAP_X)
        band_bottom = row_y + row_height + _NAMESPACE_PADDING
        namespace_bands.append((namespace, band_top, band_right + _NAMESPACE_PADDING, band_bottom))
        max_right = max(max_right, band_right + _NAMESPACE_PADDING)
        cursor_y = band_bottom + _NAMESPACE_GAP_Y

    total_height = (cursor_y - _NAMESPACE_GAP_Y + _MARGIN) if namespace_bands else _MARGIN * 2
    total_width = (max_right + _MARGIN) if namespace_bands else _MARGIN * 2
    return total_width, total_height, namespace_bands


def _clip_point_toward(box: _ClassBox, target_x: float, target_y: float) -> tuple[float, float]:
    """boxの中心から(target_x, target_y)方向への直線と、box境界との交点を返す。"""
    cx, cy = box.x + box.width / 2, box.y + box.height / 2
    dx, dy = target_x - cx, target_y - cy
    if dx == 0 and dy == 0:
        return cx, cy
    half_w, half_h = box.width / 2, box.height / 2
    candidates = []
    if dx != 0:
        candidates.append(half_w / abs(dx))
    if dy != 0:
        candidates.append(half_h / abs(dy))
    t = min(candidates) if candidates else 0.0
    return cx + dx * t, cy + dy * t


# -- SVG組み立て ---------------------------------------------------------------


def _render_class_box(box: _ClassBox, clip_id: str) -> list[str]:
    border = _BORDER_COLOR[box.status]
    border_width = _BORDER_WIDTH[box.status]
    header_fill = _HEADER_FILL[box.status]
    parts = [
        f'<rect x="{box.x:.1f}" y="{box.y:.1f}" width="{box.width:.1f}" height="{box.height:.1f}" '
        f'rx="4" fill="#ffffff" stroke="{border}" stroke-width="{border_width}"/>',
        f'<rect x="{box.x:.1f}" y="{box.y:.1f}" width="{box.width:.1f}" height="{_HEADER_HEIGHT:.1f}" '
        f'fill="{header_fill}" clip-path="url(#{clip_id})"/>',
    ]
    if box.lines:
        parts.append(
            f'<line x1="{box.x:.1f}" y1="{box.y + _HEADER_HEIGHT:.1f}" '
            f'x2="{box.x + box.width:.1f}" y2="{box.y + _HEADER_HEIGHT:.1f}" '
            f'stroke="{border}" stroke-width="1"/>'
        )
    name_style = ' text-decoration="line-through"' if box.status == "removed" else ""
    label_text = _STATUS_PREFIX[box.status] + box.label
    parts.append(
        f'<text x="{box.x + box.width / 2:.1f}" y="{box.y + _HEADER_HEIGHT / 2 + 4:.1f}" '
        f'font-family="{_FONT_STACK}" font-size="13" font-weight="bold" text-anchor="middle"'
        f'{name_style} fill="#1f2328">{_escape(label_text)}</text>'
    )

    y = box.y + _HEADER_HEIGHT
    for line in box.lines:
        bg = _LINE_BG[line.status]
        if bg:
            parts.append(
                f'<rect x="{box.x + 1:.1f}" y="{y:.1f}" width="{box.width - 2:.1f}" '
                f'height="{_LINE_HEIGHT:.1f}" fill="{bg}"/>'
            )
        symbol = _GUTTER_SYMBOL[line.status]
        if symbol:
            parts.append(
                f'<text x="{box.x + _GUTTER_WIDTH / 2:.1f}" y="{y + _LINE_HEIGHT * 0.7:.1f}" '
                f'font-family="{_FONT_STACK}" font-size="12" font-weight="bold" text-anchor="middle" '
                f'fill="{_GUTTER_COLOR[line.status]}">{symbol}</text>'
            )
        text_style = ' text-decoration="line-through"' if line.status == "removed" else ""
        parts.append(
            f'<text x="{box.x + _GUTTER_WIDTH + 4:.1f}" y="{y + _LINE_HEIGHT * 0.7:.1f}" '
            f'font-family="{_FONT_STACK}" font-size="12"{text_style} '
            f'fill="#1f2328">{_escape(line.text)}</text>'
        )
        y += _LINE_HEIGHT
    return parts


def _render_relation(relation: RelationIR, boxes: dict[str, _ClassBox], *, added: bool) -> list[str]:
    src, tgt = boxes[relation.source_fqn], boxes[relation.target_fqn]
    src_cx, src_cy = src.x + src.width / 2, src.y + src.height / 2
    tgt_cx, tgt_cy = tgt.x + tgt.width / 2, tgt.y + tgt.height / 2
    p1 = _clip_point_toward(src, tgt_cx, tgt_cy)
    p2 = _clip_point_toward(tgt, src_cx, src_cy)

    color = _RELATION_COLOR[added]
    dash = "" if added else ' stroke-dasharray="6,4"'
    suffix = "added" if added else "removed"
    if relation.type == RelationType.INHERITANCE:
        marker = f' marker-end="url(#arrow-inherit-{suffix})"'
    else:
        marker = f' marker-start="url(#diamond-compose-{suffix})"'

    mid_x, mid_y = (p1[0] + p2[0]) / 2, (p1[1] + p2[1]) / 2
    label = _RELATION_LABEL[added]
    label_width = max(28, len(label) * 7 + 8)
    return [
        f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" y2="{p2[1]:.1f}" '
        f'stroke="{color}" stroke-width="1.5"{dash}{marker}/>',
        f'<rect x="{mid_x - label_width / 2:.1f}" y="{mid_y - 15:.1f}" width="{label_width:.1f}" height="14" '
        f'fill="#ffffff" stroke="{color}" rx="2"/>',
        f'<text x="{mid_x:.1f}" y="{mid_y - 5:.1f}" font-family="{_FONT_STACK}" font-size="10" '
        f'text-anchor="middle" fill="{color}">{label}</text>',
    ]


def _build_defs(boxes: dict[str, _ClassBox], clip_ids: dict[str, str]) -> list[str]:
    parts = ["<defs>"]
    for fqn, box in boxes.items():
        parts.append(
            f'<clipPath id="{clip_ids[fqn]}"><rect x="{box.x:.1f}" y="{box.y:.1f}" '
            f'width="{box.width:.1f}" height="{_HEADER_HEIGHT:.1f}" rx="4"/></clipPath>'
        )
    for suffix, color in (("added", _RELATION_COLOR[True]), ("removed", _RELATION_COLOR[False])):
        parts.append(
            f'<marker id="arrow-inherit-{suffix}" viewBox="0 0 12 12" refX="11" refY="6" '
            f'markerWidth="12" markerHeight="12" orient="auto">'
            f'<path d="M1,1 L11,6 L1,11 z" fill="#ffffff" stroke="{color}" stroke-width="1.2"/></marker>'
        )
        parts.append(
            f'<marker id="diamond-compose-{suffix}" viewBox="0 0 12 12" refX="1" refY="6" '
            f'markerWidth="12" markerHeight="12" orient="auto">'
            f'<path d="M1,6 L6,1 L11,6 L6,11 z" fill="{color}"/></marker>'
        )
    parts.append("</defs>")
    return parts


class GitHubStyleSvgRenderer:
    """SnapshotDiffから、mermaid非依存の自己完結SVGを直接生成する。RendererPortを満たす。"""

    def render(
        self, diff: SnapshotDiff, *, mermaid: str | None = None, meta: dict[str, str] | None = None
    ) -> str:
        del mermaid, meta  # このレンダラーはSnapshotDiffのみから完結してレンダリングする
        boxes = _collect_boxes(diff)
        total_width, total_height, namespace_bands = _layout(boxes)
        clip_ids = {fqn: f"box-clip-{i}" for i, fqn in enumerate(boxes)}

        parts: list[str] = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width:.0f}" height="{total_height:.0f}" '
            f'viewBox="0 0 {total_width:.0f} {total_height:.0f}" font-family="{_FONT_STACK}">',
            '<rect width="100%" height="100%" fill="#ffffff"/>',
        ]
        parts.extend(_build_defs(boxes, clip_ids))

        for namespace, top, right, bottom in namespace_bands:
            if namespace is None:
                continue
            parts.append(
                f'<rect x="{_MARGIN:.1f}" y="{top:.1f}" width="{right - _MARGIN:.1f}" '
                f'height="{bottom - top:.1f}" rx="6" fill="none" stroke="#d0d7de" '
                f'stroke-dasharray="4,3"/>'
            )
            parts.append(
                f'<text x="{_MARGIN + 8:.1f}" y="{top + 16:.1f}" font-family="{_FONT_STACK}" font-size="12" '
                f'fill="#57606a">{_escape(namespace)}</text>'
            )

        for fqn, box in boxes.items():
            parts.extend(_render_class_box(box, clip_ids[fqn]))

        for relation in diff.relations.added:
            parts.extend(_render_relation(relation, boxes, added=True))
        for relation in diff.relations.removed:
            parts.extend(_render_relation(relation, boxes, added=False))

        parts.append("</svg>")
        return "".join(parts)
