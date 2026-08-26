# demo_shop

A tiny fixture package that exists **only** to produce a live, permanent demo
pull request showing what design-diff's own PR comment looks like in
practice. It is not imported or used by the `design_diff` tool itself.

The story matches [`docs/examples/shop-discount-codes.md`](../docs/examples/shop-discount-codes.md):
a small online shop's model layer gains a "discount code" feature. See the
sample PR linked from the README for the live result.

This package (and its dedicated workflow,
`.github/workflows/design-diff-demo.yml`) is intentionally isolated from the
main `design-diff-comment.yml` workflow, which analyzes the `design_diff`
package itself.
