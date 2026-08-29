# design-diff

**See what a pull request does to your architecture — classes, members, and dependencies — as a GitHub-style diff, rendered as one picture in the PR comment.**

![design-diff output: a class diagram where added members are green rows with a + gutter, removed members are red rows with strikethrough, and a new dependency is drawn as a labeled green edge](https://raw.githubusercontent.com/t29mato/design-diff/main/docs/images/shop-discount-codes.svg)

![The same diagram as it actually renders inside a live GitHub pull request comment](https://raw.githubusercontent.com/t29mato/design-diff/main/docs/images/pr-comment-live-demo.png)
*This is a real PR comment, not a mockup — click through: [sample PR #8](https://github.com/t29mato/design-diff/pull/8).*

A 500-line diff tells you *how much* changed. design-diff tells you *what* changed: which classes appeared or disappeared, which properties and methods were added or removed inside each class, and which dependencies grew between them. Added members are green rows with a `+` gutter, removed members are red rows with strikethrough — the same visual language as the code diff you already read every day.

## Quick start (GitHub Action)

Add one workflow, and every pull request gets an architecture diff comment automatically:

```yaml
# .github/workflows/design-diff-comment.yml
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

The comment is updated in place on every push (no notification floods), and stays silent when nothing structural changed.

## Quick start (CLI)

```bash
uv add design-diff   # or: pip install design-diff

design-diff diff main HEAD --package your_package_name --format svg > diff.svg
```

Compare any two git refs — branches, tags, or commits — and get the same picture locally before you open the PR.

## Machine-readable output for AI reviewers

```bash
design-diff diff main HEAD --package your_package_name --format json
```

Returns a self-contained JSON document — added/removed/modified classes, member-level changes, dependency edges, and analysis warnings — designed to be dropped straight into an LLM reviewer's context.

## MCP server (for agents and other MCP clients)

design-diff also ships an [MCP](https://modelcontextprotocol.io) server exposing a single tool, `analyze_design_diff` (two git refs + a package name → the same JSON as `--format json`), so an agent can request an architecture diff directly instead of shelling out to the CLI.

```bash
uv add design-diff
uv run design-diff-mcp   # stdio server; register it with your MCP client, don't run it standalone
```

Register it with your MCP client by pointing it at the `design-diff-mcp` command, for example in a generic `mcp.json`:

```json
{
  "mcpServers": {
    "design-diff": {
      "command": "uv",
      "args": ["run", "design-diff-mcp"],
      "cwd": "/absolute/path/to/your/repo"
    }
  }
}
```

`cwd` is the repository to analyze (`repo_path` can also be passed per-call as a tool argument to override it). See [AGENTS.md](https://github.com/t29mato/design-diff/blob/main/AGENTS.md) for client-specific registration steps (Claude Code, Claude Desktop, etc.).

## How it works

design-diff checks out both refs into temporary worktrees, imports the package in each snapshot (in isolated subprocesses), extracts the class structure — inheritance and composition from type annotations, resolved with `typing.get_type_hints()` — and diffs the two structures. Rendering is a pure function of that diff. Unlike exploratory, presentation-oriented architecture visualizers, design-diff is deterministic, runs as a CI-enforced check on every pull request, and involves no LLM — the diagram is a pure function of two code snapshots, not a generated summary.

## Requirements & limitations

- **Python 3.12+**, analyzing Python packages.
- **Dependencies of the analyzed package must be installed** — analysis imports the code, so anything the package imports must be importable. In CI this is already true for your own repository.
- **Type annotations drive dependency detection.** Unannotated code still diffs classes and members, but composition edges won't appear.
- **Analysis executes module-level code** (imports run it). Only analyze code you trust — the bundled workflow skips fork PRs and passes no secrets for exactly this reason.
- If some submodule fails to import, the diff is still produced and the failure is reported as a warning — a "no changes" result is only claimed when the whole package was analyzed.

## License

[MIT](https://github.com/t29mato/design-diff/blob/main/LICENSE)
