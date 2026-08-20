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
posts the diagram as a PR comment — updated in place on every push, silent
when nothing structural changed.

Example output (real, unedited CLI run) — a PR that adds a DiscountCode
class, removes a LegacyCouponBanner class, and changes Cart/Product:
https://github.com/t29mato/design-diff/blob/main/docs/examples/shop-discount-codes.md

It's an early MVP (v0.1.0), built with a clean-architecture separation
between the extraction backend (currently py2puml) and everything else, so
the extraction strategy can be swapped later without touching the diffing
or rendering logic. I ran it against five real-world PyPI packages
(requests, flask, click, rich, httpx) before posting this, specifically
looking for crashes, hangs, or silent failures on code I didn't write — all
five completed successfully. The main real limitation right now: it needs
type annotations to detect dependencies (it can't infer relationships from
untyped code), and the target package's own runtime dependencies need to be
installed wherever design-diff runs, since it analyzes code by importing it
rather than just parsing the AST.

Repo: https://github.com/t29mato/design-diff

I'd like feedback on whether the diagram is actually the right level of
abstraction for PR review, and on the "execute code to analyze it" tradeoff
security-conscious teams that used the extraction approach.
```

## 補足(投稿前に人間が確認すべき点)

- 上記URL(docs/examples/shop-discount-codes.md)は実際にリポジトリに存在する
  ファイルへのリンク。投稿前に最新版で内容が変わっていないか確認すること
- 実戦テストの結果(5パッケージ完走)は
  [docs/design/investigations/real-world-package-testing.md](../design/investigations/real-world-package-testing.md)
  の内容と整合させてあるが、投稿時点で内容が古くなっていないか確認すること
- バージョン番号(v0.1.0)が投稿時点のものと一致しているか確認すること
