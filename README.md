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

### 出力例(抜粋)

`design-diff diff main feature/discount-codes --package shop --format mermaid` の
実際の出力(手を加えていない。完全版は
[docs/examples/shop-discount-codes.md](./docs/examples/shop-discount-codes.md)):

```mermaid
classDiagram
    namespace shop.models {
        class shop_models_Cart["[~] Cart"] {
            +items: List[Product]
            +discount_code: Optional[DiscountCode]  [+]
            +add(product: Product): None
            +apply_code(code: DiscountCode): None  [+]
            +total(): float
        }
        class shop_models_DiscountCode["[+] DiscountCode"] {
            +code: str
            +percent_off: float
        }
        class shop_models_LegacyCouponBanner["[-] LegacyCouponBanner"] {
            +text: str
        }
    }
    style shop_models_Cart fill:#fff8e6,stroke:#b08800,stroke-width:2px,color:#b08800
    style shop_models_DiscountCode fill:#e6ffed,stroke:#22863a,stroke-width:2px,color:#22863a
    style shop_models_LegacyCouponBanner fill:#ffeef0,stroke:#b31d28,stroke-width:2px,color:#b31d28
    shop_models_Cart *-- shop_models_DiscountCode
```

`DiscountCode`クラスの追加(緑)、`LegacyCouponBanner`クラスの削除(赤)、`Cart`の
変更(黄。`discount_code`/`apply_code()`が新しく増えたメンバーだと行末の`[+]`で
分かる)、`Cart *-- DiscountCode`という新しいコンポジション依存が、1枚の図に
収まっている。

## 使い方

```bash
uv add design-diff
design-diff diff main feature/my-branch --package myapp --format mermaid
```

`--format` は `mermaid`(既定) / `json` / `svg` を選べる。

## どこでプレビューするか(重要)

- **GitHubのPRコメント**: GitHubは ```` ```mermaid ```` フェンスで囲まれたコードブロックを
  ネイティブにクラス図としてレンダリングする。design-diffのGitHub Actionワークフロー
  (`.github/workflows/design-diff-comment.yml`)はこの形式でコメントを投稿するので、
  **追加の設定なしにPR上で絵として見える**。README上のMermaidブロックも同様に
  GitHub上でプレビューされる(このREADME自体、[docs/examples/](./docs/examples/)の
  ブロックがその実例)
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

> **調査メモ**: Node.js/Puppeteer(Chromium)を要求しないSVG化経路(`mermaidx`という
> Python製パッケージ)の存在を実機検証済み。乗り換えの投資判断はまだしていない。
> 詳細は [docs/design/investigations/mermaid-svg-without-chromium.md](./docs/design/investigations/mermaid-svg-without-chromium.md)。

## 出力の読み方

- `[+]` = 追加されたクラス、`[-]` = 削除されたクラス、`[~]` = 変更されたクラス。
  ラベルのASCIIタグに加えて、`style`文で実際に色も付く(追加=緑/削除=赤/変更=黄、
  クラス単位)。詳細は下記「表示に関する注記」を参照
- **変更されたクラスは、どのproperty/methodが増減したかをメンバー行自体に示す**。
  追加された属性/メソッドの行末に`[+]`、変更された行末に`[~]`(型変更の場合は
  `(was: <旧の型>)`も付く)。削除された属性/メソッドはheadにはもう存在しないが、
  クラス本体の中に`[-]`付きで表示される(クラス単位の`note`要約とは別に、本体を
  見るだけで「このクラスの何が変わったか」まで分かるようにするため)
- 可視性マーカー `+`(public) / `-`(private) で、アンダースコア始まりのメンバーを
  区別する。クラスの公開APIが一目で分かる
- 変更のないクラスは図に出さない(ノイズ削減)
- 変更されたクラス数が既定20を超える大きなPRでは、影響度(差分の大きさ)順に
  上位20件だけを図示し、省略件数を`note`で明示する。完全な一覧は`--format json`で
- `--include-dunder` を付けない限り、`__init__`等のダンダーメソッドは表示しない
  (dataclass自動生成やProtocolのボイラープレートで図がノイズだらけになるのを防ぐため)

### 表示に関する注記: 色分けの実現方法

当初はMermaidの`classDef`+`cssClass`による色分け(追加=緑/削除=赤/変更=黄)を
実装していたが、GitHubのPRコメントおよびmermaid.live双方で実機検証したところ、
**classDiagramの`cssClass`スタイリングが全く反映されない**ことが判明した。
design-diff固有の不具合ではなく、Mermaid本体側の既知の問題
([mermaid-js/mermaid#1649](https://github.com/mermaid-js/mermaid/issues/1649))。

その後、ノード単体を対象にする**`style <id> fill:...,stroke:...;`文**(`classDef`/
`cssClass`とは別のMermaid機構)を検証したところ、GitHubの実機(namespace記法・
ラベル・メソッド本文と併用した状態)で緑/赤/黄が実際に描画されることを確認できた
([docs/design/architecture.md](./docs/design/architecture.md) §7参照)。これは
GitHub固有の裏技ではなく標準Mermaid構文なので、GitLab等の他のMermaid実装でも
動作する見込みだが、GitHub以外での実機確認はまだ行っていない。

`fill`/`stroke`だけを指定した最初の実装では、背景色・枠線は変わるのに
タイトル・メンバーの文字自体はテーマ既定の薄いグレーのまま残ってしまい、
色分けの効果が薄いという指摘を受けた。`style`文に**`color`(文字色)も指定**する
ことで、GitHub実機でタイトル・メンバー行とも状態色で塗られることを確認済み。

**ただし`style`文はノード(クラス)単位にしか色を当てられず、メンバー(property/
method)1つ1つには適用できない**。そのため「このクラスの、どのproperty/method
そのものが増えた/減ったか」は色ではなくメンバー行自体へのASCIIタグ(`[+]`/`[-]`/`[~]`)
で表現している。カスタムSVGでメンバー単位の色分けを実現する案も検討したが、
GitHub上で生の`<svg>`タグと`<img src="data:...">`の両方が実機検証でサニタイズ
(除去)されることを確認しており、GitHub PRコメントへ直接埋め込む手段としては
使えない(README/ローカルファイルとしてなら`--format svg`で問題なく使える)。

絵文字(🟢/🔴/🟡)による代替も検討したが、環境によって絵文字グリフを持たない場合が
あり、グローバルな利用を前提にできないため不採用とした。ASCIIタグ(`[+]`/`[-]`/`[~]`)
は色分けの冗長化として残している(色覚特性やカラー非対応ビューアでも状態が
読み取れるようにするため)。JSON出力やnote内の差分表記とも記法が一貫している。

## GitHub Action(PRコメント自動投稿)

`.github/workflows/design-diff-comment.yml` は、PRのopen/更新のたびにbase...headの
設計diffを計算し、Mermaidブロックをコメントとして投稿する。

- **コメントはupsertする**: 同一PRで何度pushしても新規コメントは積み上がらず、
  隠しマーカー(`<!-- design-diff:auto-comment -->`)で見つけた既存コメントを更新する。
  通知の洪水を避けるため
- **沈黙原則**: `has_changes` が false(クラス構造に変化なし)のときはコメント自体を
  投稿しない
- **セキュリティ**: `pull_request_target` は使わない。フォークからのPRは
  ジョブ自体をスキップする(`if: github.event.pull_request.head.repo.full_name ==
  github.repository`)ため、信頼できないコードに対してpy2pumlのimportベース解析を
  実行することも、シークレットを渡すこともない。使うのは自動発行される
  `GITHUB_TOKEN` のみ(`permissions: pull-requests: write` で最小権限に絞る)

**動作確認済み**: design-diffはpublicリポジトリなのでGitHub Actionsは無料枠が
無制限。実際にPRを作成し、`gh`での手動実行ではなく本物のpull_requestイベント
経由で本ワークフローが自動実行され、コメントが投稿されてMermaid図として描画
されること、2回目以降のpushで同一コメントがupsertされること(新規コメントが
積み上がらない)、構造変化の無いPRではコメント自体が投稿されないこと(沈黙
原則)を確認済み。

## JSON出力(LLMO / AIレビュアー向け)

`--format json` は自己完結したJSONを出力する。`mermaid`フィールドに描画済みの
Mermaidブロックも同梱されるため、JSON単体でも人間可読な図をAIレビュアーが
再現できる。スキーマは [docs/design/architecture.md](./docs/design/architecture.md) §6 を参照。

## 制約・セキュリティ(Limitations & Security)

- **Limitations**: **型アノテーションが無いコードでは依存が出ない**。design-diffは
  型アノテーションから継承・コンポジション依存を抽出する。型アノテーション文化を
  促進するツールでもある、と割り切っている
- **Limitations**: **解析対象パッケージ自身の実行時依存関係が必要**。design-diffは
  対象コードを実際にimportして解析するため(下記Security参照)、対象パッケージが
  依存するライブラリ(例: httpxなら`httpcore`/`certifi`等)も、design-diffを実行
  している環境にインストールされている必要がある(design-diff自身の依存の問題では
  ない)。無い場合は`ModuleNotFoundError`になるが、これはimportベースで解析する
  以上避けられない性質で、design-diffのバグではない。CLI/GitHub Actionのエラー
  メッセージにも「対象パッケージ自身の依存をインストールしてください」という
  案内が出る。GitHub ActionでPRに対して実行する通常の文脈では、対象リポジトリ
  自身のCIで依存が既にインストールされた環境で動かすため、実用上問題になることは
  少ない
- **実戦テスト済み**: 実在のPythonパッケージ5つ(requests/flask/click/rich/httpx)
  に対して、各パッケージ自身の依存を正しくインストールした上で実際にdesign-diffを
  実行し、**全て解析が完走する**ことを確認済み(クラッシュ・無限ループ・異常な
  長時間実行も無い)。開発途中でflask/click/rich/httpxの4つが解析失敗する問題が
  見つかったが、真因(importのエイリアス・循環import回避のためのTYPE_CHECKING
  限定import・実行時コンテキスト依存オブジェクトへのアクセス)を特定し、属性の
  型解決を`typing.get_type_hints()`ベースの自前実装に置き換えることで解決した。
  詳細な経緯・最小再現コードは
  [docs/design/investigations/real-world-package-testing.md](./docs/design/investigations/real-world-package-testing.md)、
  [docs/design/investigations/py2puml-resolution-failures-root-cause.md](./docs/design/investigations/py2puml-resolution-failures-root-cause.md)
- **Security**: **対象コードを実際にimportして解析する**(ASTを静的に読むだけでは
  ない)。つまりモジュールレベルの文・デコレータ・メタクラスが実行される。
  信頼できる自分のリポジトリのコードに対してのみ実行すること。GitHub Actionは
  フォークPRに対して `pull_request_target` を使わず、シークレットも渡さない設計に
  する(詳細は [docs/design/architecture.md](./docs/design/architecture.md) §5.5, §9)

## ライセンス

MIT License。詳細は [LICENSE](./LICENSE) を参照。

依存パッケージのライセンス確認結果(2026-08-20時点、`uv tree` と各パッケージの
`License-Expression`/`License`メタデータで確認):

| パッケージ | 用途 | ライセンス |
|---|---|---|
| py2puml | 実行時(唯一の実行時依存。推移的依存なし) | MIT |
| import-linter, grimp, click, rich, markdown-it-py, mdurl, pygments, typing-extensions | 開発時のみ(配布物には含まれない) | BSD-2-Clause / MIT / PSF-2.0 |
| pytest, pytest-cov, coverage, iniconfig, packaging, pluggy | 開発時のみ | MIT / Apache-2.0 |
| ruff | 開発時のみ | MIT |

いずれも寛容(permissive)なライセンスで、MITとの互換性に問題はない。
コピーレフト(GPL系)の依存は無い。

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

### CI

publicリポジトリなので `.github/workflows/ci.yml` がpush/PRのたびに無料で
自動実行される(GitHub Actions無料枠は無制限)。これに加えて、pushする前に
同じ判定基準をローカルでも回せるようにしてある(手元でgreenを確認してから
pushしたい場合や、Actionsの結果を待たずに素早くフィードバックを得たい場合用)。

ローカルCIは `.github/workflows/ci.yml` と全く同じ順序・同じ判定基準
(ruff → import-linter → pytest+カバレッジ → ドメイン層カバレッジ90%ゲート)を
`scripts/ci.sh` として実行する:

```bash
./scripts/ci.sh
```

pushする前に自動実行させたい場合は、クローン後に一度だけ以下を実行してフックを
有効化する(`.git/hooks` はリポジトリに含まれず共有されないため、
`core.hooksPath` で `.githooks/` を指すようにしている):

```bash
./scripts/install-hooks.sh
```

以後 `git push` のたびに `scripts/ci.sh` が自動実行され、失敗すればpushが
止まる(一時的に無効化したい場合は `git push --no-verify`)。

**self-hosted runnerは採用しない**。理由: (1) 個人アカウントのrunnerはリポジトリ
単位でしか登録できず管理が煩雑、(2) マシンがスリープしているとジョブが流れない、
(3) 最大の理由として、**将来このリポジトリをpublicにした際にフォークPRからの
任意コードが自分のマシン上で実行される危険がある**ため。公開を目指すプロジェクトに
self-hosted runnerを残すのは危険な組み合わせと判断した。
