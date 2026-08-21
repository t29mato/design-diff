# Show HN 下書き(投稿はしない。人間が投稿する)

**注意**: このファイルは下書きであり、design-diffが自動で投稿することはない。
投稿するかどうか・いつ投稿するかはメンテナ本人が判断する。

## タイトル案(3つ)

1. Show HN: design-diff – See class-diagram-level diffs in your PRs, not just line diffs
2. Show HN: design-diff – A Mermaid class diagram for what actually changed in a PR
3. Show HN: design-diff – Turn a Python PR into a class diagram diff (added/removed/changed)

## 本文(英語)

```
When most of the code in a PR is written or drafted by an AI, reading a
500-line diff stops being the useful part of review. What actually matters
is: which classes got added, which got removed, and which dependencies
between them just appeared or disappeared. That's a design diff, not a
line diff, and nothing I could find showed it to me automatically.

design-diff takes two git refs (a base and a head), extracts the class
structure of a Python package from both (classes, inheritance, composition
dependencies), diffs the two structures, and renders the result as a
Mermaid class diagram plus machine-readable JSON. As a GitHub Action, it
posts the diagram straight into the PR as a comment — GitHub renders the
Mermaid block natively, no extra viewer needed — updated in place on every
push, and silent when nothing structural actually changed.

Example output (real, unedited CLI run) — a PR that adds a DiscountCode
class, removes a LegacyCouponBanner class, and changes Cart/Product:
https://github.com/t29mato/design-diff/blob/main/docs/examples/shop-discount-codes.md

Before posting this, I ran it against five real-world PyPI packages
(requests, flask, click, rich, httpx), specifically looking for crashes,
hangs, or silent failures on code I didn't write. The first pass was rough:
four of the five failed outright. The common thread was that the underlying
extraction library resolved type annotations by looking them up in a
module's runtime namespace directly — so an aliased import
(`import typing as t`) or a `TYPE_CHECKING`-guarded forward reference
(a standard way to avoid circular imports) would make it choke, even though
the code itself runs fine. Switching the type-resolution step to Python's
own `typing.get_type_hints()` — which evaluates annotations against the
module's actual globals instead of pattern-matching names — fixed all four.
All five packages now complete cleanly.

It's a young project (v0.2.0), built with a clean-architecture separation
between the extraction backend and everything else, so the extraction
strategy can be swapped or hardened without touching the diffing or
rendering logic. The main real limitations left: it needs type annotations
to detect dependencies (no inference from untyped code), and the target
package's own runtime dependencies need to be installed wherever design-diff
runs, since it analyzes code by importing it rather than only parsing the
AST.

Repo: https://github.com/t29mato/design-diff

I'd like feedback on whether the diagram is actually the right level of
abstraction for PR review, and on the "execute code to analyze it" tradeoff
for security-conscious teams evaluating this kind of extraction approach.
```

## 補足(投稿前に人間が確認すべき点)

- 上記URL(docs/examples/shop-discount-codes.md)は実際にリポジトリに存在する
  ファイルへのリンク。投稿前に最新版で内容が変わっていないか確認すること
- 実戦テストの結果(5パッケージ完走、当初4/5失敗→get_type_hints()採用で解決)は
  [docs/design/investigations/real-world-package-testing.md](../design/investigations/real-world-package-testing.md)
  および
  [docs/design/investigations/py2puml-resolution-failures-root-cause.md](../design/investigations/py2puml-resolution-failures-root-cause.md)
  の内容と整合させてあるが、投稿時点で内容が古くなっていないか確認すること
- バージョン番号(v0.2.0)が投稿時点のものと一致しているか確認すること
- 本文は「py2pumlが」のような固有名詞を出さず「underlying extraction
  library」という表現に留めている(実装詳細より技術的な教訓を伝える意図)。
  投稿前に、この抽象度で問題ないか・具体名(py2puml)を出したいか判断すること
