# AGENTS.md

design-diff — a class-level architecture diff for Python, rendered as a
GitHub-diff-style SVG in the PR comment. This file has three parts:

1. **Adopting design-diff into another repository** — for an agent whose task
   is "add design-diff to this repo" / "set up architecture-diff PR comments".
2. **Registering the MCP server** — for an agent whose task is "give me/my
   agent tool access to design-diff" via [MCP](https://modelcontextprotocol.io).
3. **Contributing to design-diff itself** — for an agent modifying this
   repository's own source.

---

## Part 1: Adopting design-diff into another repository

Follow these steps in order. They take you from nothing to a working PR
comment.

### 1. Confirm this is a fit

design-diff analyzes Python packages and detects inheritance/composition
dependencies from type annotations. Unannotated code still diffs classes and
members, but dependency edges won't appear. If the target repo isn't Python,
stop here and say so.

### 2. Determine the `--package` name

This is the importable top-level package name to analyze, not the PyPI
distribution name. Look for it, in order:

- `[project].name` in `pyproject.toml` (normalize dashes to underscores)
- a `src/<name>/__init__.py` or top-level `<name>/__init__.py`
- if still ambiguous (monorepo, multiple packages), ask the user

### 3. (Optional but recommended) Verify locally first

```bash
uv add design-diff   # or: pip install design-diff, if the repo doesn't use uv
design-diff diff <an-earlier-ref> HEAD --package <package_name> --format svg > /tmp/design-diff-check.svg
```

Open the SVG and sanity-check the package name is right and the diagram looks
reasonable, before wiring up the Action. Skip this step if there's no earlier
ref worth diffing against yet.

### 4. Add the GitHub Actions workflow

Create `.github/workflows/design-diff-comment.yml` with this exact content
(this is the same template shown in design-diff's own README "Quick start
(GitHub Action)" section — keep them in sync if you change one), replacing
`your_package_name` with the value from step 2:

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

If the target repo doesn't manage Python dependencies with `uv`, adapt the
`uv sync`/`uv run` steps to however it does (e.g. `pip install -e .` then
`pip install design-diff` then run `python -m design_diff.action.main ...`
directly). Either way, make sure `design-diff` itself is installed in the job
(add it to the repo's dependencies, or install it as a separate step) — the
workflow above assumes `uv sync` already resolves it because it's listed in
that repo's `pyproject.toml`/`uv.lock`.

### 5. Commit and push

Commit the workflow file (and any dependency addition) following the normal
commit/push rules for that session — ask for confirmation before pushing,
same as any other change.

### 6. Confirm it works

Open a pull request (any small code change touching the analyzed package) and
confirm a comment appears with the rendered image on the first successful
run. The comment updates in place on further pushes to the same PR (no
notification floods) and stays silent when nothing structural changed.

### Troubleshooting

- **`ModuleNotFoundError` in the Action logs**: the analyzed package's own
  runtime dependencies aren't installed in the job — this is not a
  design-diff bug. Make sure the dependency-install step actually installs
  the *analyzed* package's dependencies, not just design-diff's.
- **No comment on PRs from forks**: intentional. The `if:` condition skips
  fork PRs, because design-diff imports and executes the analyzed code —
  only same-repo PRs are analyzed.
- **Diagram shows no dependency edges**: the analyzed classes likely lack
  type annotations on attributes / `__init__` parameters.

---

## Part 2: Registering the MCP server

design-diff ships an [MCP](https://modelcontextprotocol.io) server exposing
one tool, `analyze_design_diff` (`base_ref`, `head_ref`, `package`, optional
`repo_path` and `include_boilerplate` → the same JSON as `--format json`). Use
this when an agent should be able to request an architecture diff directly,
without shelling out to the `design-diff` CLI.

### 1. Install

```bash
uv add design-diff   # or: pip install design-diff
```

This provides a `design-diff-mcp` console script that runs the server over
stdio (the default MCP transport for local tools).

### 2. Register it with your MCP client

The registration format depends on the client. In all cases, the command is
`design-diff-mcp` (or `uv run design-diff-mcp` if design-diff is a project
dependency rather than a global install), and the working directory should be
the repository to analyze:

**Generic `mcp.json` (most MCP clients):**

```json
{
  "mcpServers": {
    "design-diff": {
      "command": "uv",
      "args": ["run", "design-diff-mcp"],
      "cwd": "/absolute/path/to/the/repo/to/analyze"
    }
  }
}
```

**Claude Code:**

```bash
claude mcp add design-diff -- uv run design-diff-mcp
```

Run this from inside the repository you want to analyze (Claude Code passes
its own working directory through as the server's `cwd`), or pass
`repo_path` explicitly on each `analyze_design_diff` call instead.

**Claude Desktop:** add the same `"design-diff": {...}` block shown above to
`claude_desktop_config.json`'s `mcpServers` object, then restart the app.

### 3. Verify

Ask the connected agent to call `analyze_design_diff` with two refs in the
target repository (e.g. `base_ref="main"`, `head_ref="HEAD"`, and the
package name — see Part 1, step 2 for how to determine it) and confirm it
returns the expected JSON. Do not run `design-diff-mcp` directly in a
terminal to "test" it — it speaks JSON-RPC over stdio and will just sit
there waiting for a client, not print anything.

---

## Part 3: Contributing to design-diff itself

Background and design rationale: [CLAUDE.md](./CLAUDE.md) and
[docs/design/architecture.md](./docs/design/architecture.md).

### Setup

```bash
uv sync --dev
```

Uses [uv](https://docs.astral.sh/uv/). No `pip`/`poetry`/`requirements.txt`.

### Build, test, lint

Run this before every push and make sure every step is green:

```bash
./scripts/ci.sh
```

Breakdown (same criteria as `.github/workflows/ci.yml`):

```bash
uv run ruff check .                                                          # lint
uv run lint-imports                                                          # layer boundary enforcement
uv run pytest --cov --cov-report=term-missing --cov-report=xml               # tests + coverage
uv run coverage report --include="src/design_diff/domain/*" --fail-under=90  # domain-layer coverage gate
```

Run `./scripts/install-hooks.sh` once after cloning to make this run
automatically as a pre-push hook.

### Code conventions

- **Clean architecture**: `domain` (pure IR + diff algorithm, zero dependency
  on py2puml/git/GitHub APIs) → `application` (Protocol-based ports + use
  cases) → `adapters` (py2puml extraction, git worktree, Mermaid/JSON/native
  GitHub-diff-style SVG rendering, GitHub comment posting, SVG asset
  publishing to the `design-diff-assets` branch) → `cli`/`action`
  (composition roots). Dependencies flow one way only:
  `cli|action → application → adapters → domain`.
- **Don't loosen the 4 import-linter contracts** (`.importlinter`). CI
  failing on a layer violation is intentional; loosening it needs maintainer
  approval.
- **TDD**: tests first. `domain` layer coverage target is 90% (enforced by a
  CI gate).
- Type annotations are required (design-diff itself extracts dependencies
  from type annotations via py2puml, so it should be a model example of the
  practice it promotes).

### Design changes

Architecture or technology-choice changes need a class-level design
(Mermaid classDiagram) and a dependency-direction rationale in
`docs/design/` *before* implementation starts. Spikes/investigations only go
in `docs/design/spikes/` (delete after verifying) or
`docs/design/investigations/` (permanent record).

### Commits & branches

- Direct commits/pushes to `main` are allowed (small early-stage project).
  Confirm `./scripts/ci.sh` is green before pushing.
- Tags, GitHub Releases, PyPI publishing, and loosening CI enforcement need
  human maintainer approval. An agent must not do these unilaterally.

### Dogfooding

Run design-diff on your own PR to check the design diff itself reads well:

```bash
uv run design-diff diff main <your-branch> --package design_diff --format mermaid
```

To see the image form actually used in PR comments (native GitHub-diff-style
SVG), use `--format svg > diagram.svg` and open the file.

See [docs/examples/](./docs/examples/) for real output examples.
