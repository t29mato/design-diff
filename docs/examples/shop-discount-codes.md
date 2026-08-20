# 出力例: `shop` パッケージへの機能追加

小さなオンラインショップのモデル層に「割引コード」機能を追加したケース。
`design-diff diff main feature/discount-codes --package shop --format mermaid`
の実際の出力(手を加えていない)。

- `DiscountCode` クラスが追加された(`[+]`)
- `LegacyCouponBanner` クラスが削除された(`[-]`)
- `Cart` / `Product` が変更された(`[~]`) — 何が増減したかは `note` に要約される
- `Cart *-- DiscountCode` というコンポジション依存が新たに生えた

状態はラベルのASCIIタグ(`[+]`/`[-]`/`[~]`)と、`style`文による実際の色分け
(追加=緑/削除=赤/変更=黄)の両方で示す。当初はMermaidの`classDef`/`cssClass`による
色分けを検討したが、GitHub・mermaid.live双方の実機検証でclassDiagramのスタイリングが
全く反映されないことを確認した(design-diff固有ではなくupstream Mermaidの既知の問題。
[mermaid-js/mermaid#1649](https://github.com/mermaid-js/mermaid/issues/1649))。
一方、ノード単体を対象にする`style <id> fill:...,stroke:...;`文は別のMermaid機構であり、
GitHub実機(namespace記法併用時含む)で緑/赤/黄が実際に描画されることを確認済み。
絵文字での代替も検討したが、環境によって絵文字グリフを持たない場合がありグローバルな
利用を想定すると前提にできないため不採用。ASCIIタグは色だけに頼らないための冗長化
として残している(色覚特性やカラー非対応ビューアでも状態が読み取れるように)。

このMermaidブロックはGitHubのコメント/README上でそのままプレビューされる。

```mermaid
classDiagram
    namespace shop.models {
        class shop_models_Cart["[~] Cart"] {
            +items: List[Product]
            +discount_code: Optional[DiscountCode]
            +add(product: Product): None
            +apply_code(code: DiscountCode): None
            +total(): float
        }
        class shop_models_DiscountCode["[+] DiscountCode"] {
            +code: str
            +percent_off: float
        }
        class shop_models_LegacyCouponBanner["[-] LegacyCouponBanner"] {
            +text: str
        }
        class shop_models_Product["[~] Product"] {
            +name: str
            +price: float
            +category: Category
            +apply_discount(percent: float, code: Optional[DiscountCode]): float
        }
    }
    style shop_models_Cart fill:#fff8e6,stroke:#b08800,stroke-width:2px
    style shop_models_DiscountCode fill:#e6ffed,stroke:#22863a,stroke-width:2px
    style shop_models_LegacyCouponBanner fill:#ffeef0,stroke:#b31d28,stroke-width:2px
    style shop_models_Product fill:#fff8e6,stroke:#b08800,stroke-width:2px
    note for shop_models_Cart "+ discount_code: Optional[DiscountCode]\n+ apply_code()"
    note for shop_models_Product "~ apply_discount()"
    shop_models_Cart *-- shop_models_DiscountCode
```

## 対応するJSON出力(抜粋)

AIレビュアーやCI連携が読む機械可読フォーマット。`summary` を見るだけで
規模感(追加1・削除1・変更2・依存追加1)が分かる。完全な出力は
`design-diff diff ... --format json` で得られるオブジェクト全体(`classes`配下に
属性・メソッドの完全な差分、`mermaid`フィールドに上のMermaidブロックも同梱される)。

```json
{
  "schema_version": "1.0",
  "tool": "design-diff",
  "package": "shop",
  "base_ref": "main",
  "head_ref": "feature/discount-codes",
  "has_changes": true,
  "summary": {
    "classes_added": 1,
    "classes_removed": 1,
    "classes_modified": 2,
    "relations_added": 1,
    "relations_removed": 0
  }
}
```
