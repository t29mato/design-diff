# 出力例: `shop` パッケージへの機能追加

小さなオンラインショップのモデル層に「割引コード」機能を追加したケース。
`design-diff diff main feature/discount-codes --package shop --format mermaid`
の実際の出力(手を加えていない)。

- `DiscountCode` クラスが追加された(緑)
- `LegacyCouponBanner` クラスが削除された(赤)
- `Cart` / `Product` が変更された(黄) — 何が増減したかは `note` に要約される
- `Cart *-- DiscountCode` というコンポジション依存が新たに生えた

このMermaidブロックはGitHubのコメント/README上でそのままプレビューされる。

```mermaid
classDiagram
    classDef added fill:#e6ffed,stroke:#22863a,color:#22863a
    classDef removed fill:#ffeef0,stroke:#b31d28,color:#b31d28
    classDef modified fill:#fff8e6,stroke:#b08800,color:#7a5c00

    namespace shop.models {
        class shop_models_Cart["Cart"]:::modified {
            +items: List[Product]
            +discount_code: Optional[DiscountCode]
            +add(product: Product): None
            +apply_code(code: DiscountCode): None
            +total(): float
        }
        class shop_models_DiscountCode["DiscountCode"]:::added {
            +code: str
            +percent_off: float
        }
        class shop_models_LegacyCouponBanner["LegacyCouponBanner"]:::removed {
            +text: str
        }
        class shop_models_Product["Product"]:::modified {
            +name: str
            +price: float
            +category: Category
            +apply_discount(percent: float, code: Optional[DiscountCode]): float
        }
    }
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
