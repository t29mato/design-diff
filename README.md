# design-diff

> **design-diff** compares two Python code snapshots (`base_ref`, `head_ref`) and
> outputs a class-level structure diff — added/removed/modified classes, inheritance,
> composition dependencies — as a Mermaid `classDiagram` and machine-readable JSON.
> Install: `uv add design-diff` (or `pip install design-diff`). Run:
> `design-diff diff <base_ref> <head_ref> --package <pkg> --format mermaid|json|svg`.
> Requires type annotations to detect dependencies (see Limitations below).
> Executes the analyzed code via import — only run against trusted (same-repo) code;
> see Security below.

AIがコードを書く時代、人間のレビューは行diffから設計diffへ上がる。「500行変わった」
ではなく「このクラスが増え、この依存が生えた」を**1枚の絵**で見せるのが design-diff
の価値。文字ベースのdiffではなく、**Mermaidのクラス図としてプレビューできること**が
このツールの中心的な価値であり、それ以外の全ての設計判断はこの1点に従属する。

出力例(実際にCLIを実行した結果、手を加えていない): [docs/examples/](./docs/examples/)

## 使い方

```bash
uv add design-diff
design-diff diff main feature/my-branch --package myapp --format mermaid
```

`--format` は `mermaid`(既定) / `json` / `svg` を選べる。

## どこでプレビューするか(重要)

- **GitHubのPRコメント**: GitHubは ```` ```mermaid ```` フェンスで囲まれたコードブロックを
  ネイティブにクラス図としてレンダリングする。design-diffのGitHub Action(準備中)は
  この形式でコメントを投稿するので、**追加の設定なしにPR上で絵として見える**。
  README上のMermaidブロックも同様にGitHub上でプレビューされる
  (このREADME自体、[docs/examples/](./docs/examples/)のブロックがその実例)
- **ローカルCLI利用時**: ターミナルにMermaidのテキストが出るだけではプレビューできない。
  次の3つの方法がある:
  1. `--format svg` でSVGを直接出力する(下記参照。要 [mermaid-cli](https://github.com/mermaid-js/mermaid-cli))
  2. 出力を `.mmd` ファイルに保存し、エディタのMermaid拡張(VS Codeの
     "Markdown Preview Mermaid Support" 等)で開く
  3. [mermaid.live](https://mermaid.live) にテキストを貼り付ける(インストール不要)

### ローカルSVG出力(`--format svg`)

```bash
design-diff diff main feature/my-branch --package myapp --format svg > diagram.svg
```

design-diff自身はNode.js/Puppeteerのような重い依存を持たない。既に
[mermaid-cli](https://github.com/mermaid-js/mermaid-cli)(`mmdc`)がローカルに
インストールされていればそれを使ってSVGに変換する。無い場合はエラーと共に
インストール手順(または mermaid.live での代替方法)を案内するだけで、
design-diffが勝手にNode.jsパッケージを自動ダウンロードすることはない。

```bash
npm install -g @mermaid-js/mermaid-cli   # SVG出力を使うなら一度だけ
```

## 出力の読み方

- 🟢 緑 = 追加されたクラス、🔴 赤 = 削除されたクラス、🟡 黄 = 変更されたクラス
- 変更のないクラスは図に出さない(ノイズ削減)
- 変更されたクラス数が既定20を超える大きなPRでは、影響度(差分の大きさ)順に
  上位20件だけを図示し、省略件数を`note`で明示する。完全な一覧は`--format json`で
- `--include-dunder` を付けない限り、`__init__`等のダンダーメソッドは表示しない
  (dataclass自動生成やProtocolのボイラープレートで図がノイズだらけになるのを防ぐため)

## JSON出力(LLMO / AIレビュアー向け)

`--format json` は自己完結したJSONを出力する。`mermaid`フィールドに描画済みの
Mermaidブロックも同梱されるため、JSON単体でも人間可読な図をAIレビュアーが
再現できる。スキーマは [docs/design/architecture.md](./docs/design/architecture.md) §6 を参照。

## 制約(正直に書く)

- **型アノテーションが無いコードでは依存が出ない**。design-diffはpy2pumlを使って
  型アノテーションから継承・コンポジション依存を抽出する。型アノテーション文化を
  促進するツールでもある、と割り切っている
- **対象コードを実際にimportして解析する**(ASTを静的に読むだけではない)。
  つまりモジュールレベルの文・デコレータ・メタクラスが実行される。信頼できる
  自分のリポジトリのコードに対してのみ実行すること。GitHub ActionはフォークPRに
  対して `pull_request_target` を使わず、シークレットも渡さない設計にする
  (詳細は [docs/design/architecture.md](./docs/design/architecture.md) §5.5, §9)

## 開発

設計ドキュメント: [docs/design/architecture.md](./docs/design/architecture.md)
TDD・クリーンアーキテクチャ(domain → application → adapters → cli)・
import-linterによるレイヤー強制で開発している。

```bash
uv sync --dev
uv run pytest
uv run ruff check .
uv run lint-imports
```
