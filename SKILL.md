---
name: enable-design-diff
description: Enable design-diff's automatic architecture-diff PR comments in the current repository. Detects the Python package to analyze, optionally verifies locally, and writes the GitHub Actions workflow file. Use when the user asks to add design-diff, set up architecture-diff PR comments, or "enable design-diff here".
---

# Enable design-diff in this repository

design-diff (https://github.com/t29mato/design-diff) diffs two git refs and
renders a GitHub-diff-style picture of what changed at the class level
(classes/properties/methods added, removed, or changed; dependencies grown or
shrunk), embedded as an image in the PR comment. This skill wires that up in
the user's current repository.

> Installed this file via `npx skills add t29mato/design-diff`? You're already
> set up — just invoke the skill. This is the canonical copy; a byte-identical
> mirror lives at `.claude/skills/enable-design-diff/SKILL.md` in design-diff's
> own repo for direct use there.

Follow these steps. Do not skip the confirmation steps — pushing a workflow
file and committing to it is a real, outward-facing change.

## 1. Confirm this is a fit

Check that the current repository is a Python project (look for
`pyproject.toml`, a `setup.py`, or a package directory). design-diff detects
inheritance/composition dependencies from type annotations; unannotated code
still diffs classes and members correctly, but shows no dependency edges. If
the repo isn't Python, tell the user design-diff doesn't apply here and stop.

## 2. Determine the package name to analyze

This is the importable top-level package name (not the PyPI distribution
name), needed for the `--package` argument. Look for it, in order:

- `[project].name` in `pyproject.toml` (normalize dashes to underscores)
- a `src/<name>/__init__.py` or top-level `<name>/__init__.py` next to the
  usual source layout
- if there are multiple candidates (monorepo, multiple packages) or nothing
  obvious, ask the user which package to analyze

## 3. Offer a local sanity check (optional)

If design-diff isn't already installed and there's an earlier ref worth
diffing against (a tag, or a commit a few changes back), offer to run:

```bash
uv add design-diff   # or: pip install design-diff, if the repo doesn't use uv
design-diff diff <an-earlier-ref> HEAD --package <package_name> --format svg > /tmp/design-diff-check.svg
```

and show the user the resulting file (or describe it), to confirm the
package name is right and the diagram looks reasonable before wiring up the
Action. Skip this step if there's no earlier ref yet, or the user wants to
move straight to the workflow.

## 4. Write the GitHub Actions workflow

Create `.github/workflows/design-diff-comment.yml` with this exact content,
substituting the package name from step 2 for `your_package_name`:

```yaml
name: design-diff
on:
  pull_request:
permissions:
  contents: write        # publishes the SVG to an assets branch
  pull-requests: write   # posts / updates the PR comment
jobs:
  design-diff:
    if: github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v4
      - run: uv sync
      - env:
          GH_TOKEN: ${{ github.token }}
        run: |
          uv run python -m design_diff.action.main \
            "${{ github.event.pull_request.base.sha }}" \
            "${{ github.event.pull_request.head.sha }}" \
            --package your_package_name \
            --pr "${{ github.event.pull_request.number }}" \
            --repo "${{ github.repository }}"
```

If the repository doesn't manage Python dependencies with `uv`, adapt the
`uv sync`/`uv run` steps to however it does instead (e.g. `pip install -e .`
then `pip install design-diff`, then run `python -m design_diff.action.main
...` directly). Either way, make sure `design-diff` itself ends up installed
in the job — add it to the repository's own dependencies if the workflow
doesn't install it as a separate step.

## 5. Explain the security model if relevant

If the repository accepts external contributions, mention (proactively or if
asked): the `if:` condition skips pull requests from forks, and only the
ambient `GITHUB_TOKEN` is used — no other secrets — because design-diff
imports and executes the analyzed code, so only same-repo PRs are analyzed.

## 6. Commit and push

Commit the new workflow file (and any dependency addition from step 3/4).
This is an outward-facing, hard-to-reverse action (it will start posting
comments on future PRs) — confirm with the user before pushing, same as any
other commit in this session.

## 7. Tell the user what happens next

The next pull request that touches the analyzed package will get an
automatic comment with the architecture diagram. The comment updates in
place on further pushes to the same PR (no notification floods) and stays
silent when nothing structural changed — so silence on a PR means "no
architectural change detected," not "the Action didn't run."

## Troubleshooting

- **`ModuleNotFoundError` in the Action logs**: the analyzed package's own
  runtime dependencies aren't installed in the job. This isn't a design-diff
  bug — make sure the dependency-install step installs the *analyzed*
  package's dependencies, not just design-diff's.
- **No comment on PRs from forks**: intentional, see step 5.
- **Diagram shows no dependency edges**: the analyzed classes likely lack
  type annotations on attributes / `__init__` parameters.

See also design-diff's own [AGENTS.md](https://raw.githubusercontent.com/t29mato/design-diff/main/AGENTS.md)
for the same runbook in prose form, and its [README](https://raw.githubusercontent.com/t29mato/design-diff/main/README.md)
for what the rendered output looks like.
