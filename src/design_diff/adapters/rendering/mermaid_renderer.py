"""MermaidRenderer。RendererPortの実装。architecture.md §7 + レビューフィードバック(表示品質)。

合格基準: design-diff自身を解析した図をGitHubのMermaidプレビューに貼り、
スクロールせずに「何が増え、何が消え、何が変わり、どの依存が生えたか」が
一目で分かること。そのための設計判断:

- **3状態はラベルのASCIIステータスタグ(`[+]`追加 / `[-]`削除 / `[~]`変更)+
  `style`文による実際の色付け(追加=緑 / 削除=赤 / 変更=黄)の両方で示す**。
  当初は`classDef`+`cssClass`による色分けを検討したが、GitHub・mermaid.live双方の
  実機検証で「classDiagramのcssClassスタイリングが全く反映されない」ことを確認した
  (design-diff固有の不具合ではなく、upstream Mermaidの既知の問題。
  https://github.com/mermaid-js/mermaid/issues/1649 )。
  絵文字での代替も検討したが、環境によって絵文字グリフを持たない場合がある
  (グローバルな利用を想定すると前提にできない)ため採用しない。
  一方、ノード単体を対象にする`style <id> fill:...,stroke:...;`文は別の
  Mermaid機構であり、GitHub実機(namespace記法・ラベル・メソッド本文と併用した
  状態)で緑/赤/黄が実際に描画されることを確認済み。標準Mermaid構文でありGitHub
  固有の裏技ではないため、GitLab等の他のMermaid実装でも動作する可能性が高い
  (ただしGitHub以外での実機確認はまだ行っていない)。ASCIIタグは色だけに頼らない
  ための冗長化として残す(色覚特性やカラー非対応ビューアでも状態が読み取れるように
  するため。JSON出力やnote内の差分表記`+`/`-`/`~`とも記法が一貫する)
- **表示ラベルは短いクラス名にし、fqnはノードID(内部識別子)としてのみ使う**。
  fqnをそのままラベルにすると `design_diff.application.use_cases.compute_design_diff.
  ComputeDesignDiffUseCase` のような長大な文字列が並び、図として破綻する。
  Mermaidの `class <id>["<label>"]` 構文で、IDと見た目のラベルを分離する
- **モジュールパス(fqnの最後の要素を除いた部分)を namespace としてグループ化**する。
  同じファイルに定義されたクラスは近くに描画され、大きなリポジトリでも構造が読める
- ノードIDはfqnのドットをアンダースコアに置換して生成する(Mermaidの識別子として
  安全かつ一意)。バッククォート記法は使わない(ラベルで代替するため不要)
- modified クラスは head 時点の全属性/メソッドを表示し、差分サマリを note で添える
  (Mermaidの `+`/`-` は可視性(public/private)の意味で予約されているため、
  診断結果の追加/削除をメンバー行の先頭に流用しない。noteの中はプレーンテキストなので
  git diff風の `+`/`-` を安全に使える)
- 変更のないクラスは出さない(ノイズ削減)。リレーションの参照先が非変更クラスの
  場合のみ、文脈として装飾なしのラベルだけを宣言する
- **図のサイズ制御(追加要件)**: 変更クラス数が `max_classes`(既定20)を超えたら、
  差分の大きさ(影響度)順に上位N件だけを図示し、残りは`note "..."`
  (標準Mermaid構文)で要約する。Markdown表などは混ぜない
  ―― GitHubのPRコメントプレビューだけでなく、mermaid-cli等によるSVG変換にも
  そのまま渡せる、純粋なMermaidテキストであり続けるようにするため
"""

from __future__ import annotations

from design_diff.domain.diff import AttributeDiff, ClassModification, MethodDiff, SnapshotDiff
from design_diff.domain.model import AttributeIR, ClassIR, MethodIR, RelationIR, RelationType

_STATUS_TAG = {
    "added": "[+] ",
    "removed": "[-] ",
    "modified": "[~] ",
}

# `style <id> fill:<fill>,stroke:<stroke>,stroke-width:2px` として使う(fill, stroke)。
# GitHub実機(namespace併用時含む)で緑/赤/黄が実際に描画されることを確認済み。
_STYLE_COLOR = {
    "added": ("#e6ffed", "#22863a"),
    "removed": ("#ffeef0", "#b31d28"),
    "modified": ("#fff8e6", "#b08800"),
}

_RELATION_ARROW = {
    RelationType.COMPOSITION: "*--",
    RelationType.INHERITANCE: "<|--",
}

DEFAULT_MAX_CLASSES = 20


def _mermaid_id(fqn: str) -> str:
    """fqnからMermaidの識別子として安全なノードIDを作る(ドット区切りをアンダースコアに)。"""
    return fqn.replace(".", "_")


def _short_label(fqn: str) -> str:
    return fqn.rsplit(".", 1)[-1]


def _namespace(fqn: str) -> str | None:
    if "." not in fqn:
        return None
    return fqn.rsplit(".", 1)[0]


def _visibility(name: str) -> str:
    """Mermaidの可視性マーカー。命名規約に従い、アンダースコア始まりは`-`(private)。

    レビューフィードバック: 全メンバーが`+`(public)一色だと、図から公開APIが読み取れない。
    """
    return "-" if name.startswith("_") else "+"


def _render_attribute_line(attribute: AttributeIR) -> str:
    marker = _visibility(attribute.name)
    if attribute.type is None:
        # レビューフィードバック: 型注釈が無いだけなのに`None`という偽の型名が出るのを防ぐ。
        # 型が取れない場合は型部分自体を省略する。
        return f"        {marker}{attribute.name}"
    return f"        {marker}{attribute.name}: {attribute.type}"


def _render_method_line(method: MethodIR) -> str:
    params = ", ".join(f"{p.name}: {p.type}" if p.type else p.name for p in method.parameters)
    signature = f"        {_visibility(method.name)}{method.name}({params})"
    if method.return_type:
        signature += f": {method.return_type}"
    return signature


class _ClassDeclaration:
    """1クラス分のMermaid宣言(namespaceでグループ化する前の中間表現)。"""

    __slots__ = ("fqn", "node_id", "namespace", "label", "style", "body_lines")

    def __init__(self, fqn: str, style: str | None, body_lines: list[str]):
        self.fqn = fqn
        self.node_id = _mermaid_id(fqn)
        self.namespace = _namespace(fqn)
        self.label = _short_label(fqn)
        self.style = style  # "added" / "removed" / "modified" / None(文脈上の参照のみ)
        self.body_lines = body_lines

    def render(self) -> list[str]:
        tag = _STATUS_TAG.get(self.style, "") if self.style else ""
        header = f'    class {self.node_id}["{tag}{self.label}"]'
        if not self.body_lines:
            return [header]
        return [header + " {", *self.body_lines, "    }"]


def _class_body(cls: ClassIR) -> list[str]:
    lines = [_render_attribute_line(a) for a in cls.attributes]
    lines.extend(_render_method_line(m) for m in cls.methods)
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


def _modification_impact(mod: ClassModification) -> int:
    return (
        len(mod.attributes.added)
        + len(mod.attributes.removed)
        + len(mod.attributes.changed)
        + len(mod.methods.added)
        + len(mod.methods.removed)
        + len(mod.methods.changed)
        + (1 if mod.is_abstract_changed else 0)
    )


def _class_size(cls: ClassIR) -> int:
    return len(cls.attributes) + len(cls.methods)


class _ChangedClass:
    """added/removed/modifiedを、サイズ制御のために同じ形で扱うための共通ラッパー。"""

    __slots__ = ("fqn", "impact", "kind", "payload")

    def __init__(self, fqn: str, impact: int, kind: str, payload):
        self.fqn = fqn
        self.impact = impact
        self.kind = kind  # "added" / "removed" / "modified"
        self.payload = payload


class MermaidRenderer:
    def __init__(self, max_classes: int = DEFAULT_MAX_CLASSES):
        self._max_classes = max_classes

    def render(
        self,
        diff: SnapshotDiff,
        *,
        mermaid: str | None = None,
        meta: dict[str, str] | None = None,
    ) -> str:
        changed = self._collect_changed_classes(diff)
        total = len(changed)
        capped = total > self._max_classes
        selected = self._select_top_n(changed) if capped else changed

        declarations: dict[str, _ClassDeclaration] = {}
        for entry in selected:
            declarations[entry.fqn] = self._declaration_for(entry)

        relations = [*diff.relations.added, *diff.relations.removed]
        removed_relation_ids = {id(r) for r in diff.relations.removed}
        for relation in relations:
            for fqn in (relation.source_fqn, relation.target_fqn):
                declarations.setdefault(fqn, _ClassDeclaration(fqn, style=None, body_lines=[]))

        lines = ["classDiagram"]
        lines.extend(self._render_namespaced_declarations(declarations))
        lines.extend(self._render_style_lines(declarations))

        notes = self._collect_notes(selected)
        if capped:
            notes.append(self._summary_note(total, len(selected)))
        lines.extend(notes)

        for relation in relations:
            lines.append(self._render_relation_line(relation, removed=id(relation) in removed_relation_ids))

        return "\n".join(lines)

    # -- サイズ制御 -----------------------------------------------------

    def _collect_changed_classes(self, diff: SnapshotDiff) -> list[_ChangedClass]:
        changed = [_ChangedClass(c.fqn, _class_size(c), "added", c) for c in diff.classes.added]
        changed += [_ChangedClass(c.fqn, _class_size(c), "removed", c) for c in diff.classes.removed]
        changed += [
            _ChangedClass(m.fqn, _modification_impact(m), "modified", m)
            for m in diff.classes.modified
        ]
        return changed

    def _select_top_n(self, changed: list[_ChangedClass]) -> list[_ChangedClass]:
        return sorted(changed, key=lambda c: (-c.impact, c.fqn))[: self._max_classes]

    def _summary_note(self, total: int, shown: int) -> str:
        text = (
            f"{total} classes changed - showing top {shown} by impact.\\n"
            "See the JSON output for the complete list."
        )
        return f'    note "{text}"'

    # -- クラス宣言 -------------------------------------------------------

    def _declaration_for(self, entry: _ChangedClass) -> _ClassDeclaration:
        if entry.kind == "added":
            cls: ClassIR = entry.payload
            return _ClassDeclaration(cls.fqn, "added", _class_body(cls))
        if entry.kind == "removed":
            cls = entry.payload
            return _ClassDeclaration(cls.fqn, "removed", _class_body(cls))
        mod: ClassModification = entry.payload
        return _ClassDeclaration(mod.fqn, "modified", _class_body(mod.head_class))

    def _render_namespaced_declarations(self, declarations: dict[str, _ClassDeclaration]) -> list[str]:
        by_namespace: dict[str | None, list[_ClassDeclaration]] = {}
        for decl in declarations.values():
            by_namespace.setdefault(decl.namespace, []).append(decl)

        lines: list[str] = []
        for namespace in sorted(ns for ns in by_namespace if ns is not None):
            lines.append(f"    namespace {namespace} {{")
            for decl in sorted(by_namespace[namespace], key=lambda d: d.fqn):
                lines.extend(f"    {line}" for line in decl.render())
            lines.append("    }")
        for decl in sorted(by_namespace.get(None, []), key=lambda d: d.fqn):
            lines.extend(decl.render())
        return lines

    def _render_style_lines(self, declarations: dict[str, _ClassDeclaration]) -> list[str]:
        """追加/削除/変更クラスに`style`文で色を付ける(文脈上の参照のみのクラスは対象外)。"""
        lines = []
        for decl in sorted(declarations.values(), key=lambda d: d.fqn):
            if decl.style is None:
                continue
            fill, stroke = _STYLE_COLOR[decl.style]
            lines.append(f"    style {decl.node_id} fill:{fill},stroke:{stroke},stroke-width:2px")
        return lines

    # -- note(差分サマリ) ------------------------------------------------

    def _collect_notes(self, selected: list[_ChangedClass]) -> list[str]:
        notes = []
        for entry in selected:
            if entry.kind != "modified":
                continue
            mod: ClassModification = entry.payload
            note_lines = _format_attribute_diff_note(mod.attributes) + _format_method_diff_note(mod.methods)
            if mod.is_abstract_changed:
                note_lines.append("~ is_abstract changed")
            note_text = "\\n".join(note_lines)
            notes.append(f'    note for {_mermaid_id(mod.fqn)} "{note_text}"')
        return notes

    # -- リレーション -----------------------------------------------------

    def _render_relation_line(self, relation: RelationIR, *, removed: bool) -> str:
        arrow = _RELATION_ARROW[relation.type]
        line = f"    {_mermaid_id(relation.source_fqn)} {arrow} {_mermaid_id(relation.target_fqn)}"
        if removed:
            line += "  %% removed"
        return line
