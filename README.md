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

## 出力の読み方

- `[+]` = 追加されたクラス、`[-]` = 削除されたクラス、`[~]` = 変更されたクラス。
  ラベルのASCIIタグに加えて、`style`文で実際に色も付く(追加=緑/削除=赤/変更=黄)。
  詳細は下記「表示に関する注記」を参照
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

**現状(private repoの間)**: GitHub Actionsはprivateリポジトリでは課金対象になる
(publicリポジトリは無料枠が無制限)。design-diffは現在privateのため、
このワークフローは意図的に「資産としてリポジトリに残してあるが、実行はしない」
状態にしている。動作自体は自分のgh認証で `python -m design_diff.action.main` を
手動実行して検証済み(実際にPRにコメントが投稿され、Mermaid図として描画される
ところまで確認した)。public化した瞬間、このワークフローは追加設定なしに
無料で自動的に動き出す。

## JSON出力(LLMO / AIレビュアー向け)

`--format json` は自己完結したJSONを出力する。`mermaid`フィールドに描画済みの
Mermaidブロックも同梱されるため、JSON単体でも人間可読な図をAIレビュアーが
再現できる。スキーマは [docs/design/architecture.md](./docs/design/architecture.md) §6 を参照。

## 制約・セキュリティ(Limitations & Security)

- **Limitations**: **型アノテーションが無いコードでは依存が出ない**。design-diffは
  py2pumlを使って型アノテーションから継承・コンポジション依存を抽出する。
  型アノテーション文化を促進するツールでもある、と割り切っている
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

### CIはローカルで回す(private repoの間)

**このプロジェクトのCIは現在ローカルで回している。GitHub Actionsのワークフロー
(`.github/workflows/ci.yml`)は削除せず資産として残してあり、リポジトリを
public化した瞬間に追加設定なしで無料で自動的に有効になる**設計にしている
(privateリポジトリではGitHub Actionsが課金対象になるため、当面はそれを避ける)。

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
