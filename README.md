# nborder

A fast, opinionated linter and auto-fixer for Jupyter notebook hidden-state and execution-order bugs.

[![PyPI version](https://img.shields.io/pypi/v/nborder.svg)](https://pypi.org/project/nborder/)
[![CI](https://github.com/moonrunnerkc/nborder/actions/workflows/ci.yml/badge.svg)](https://github.com/moonrunnerkc/nborder/actions/workflows/ci.yml)
[![Python](https://img.shields.io/pypi/pyversions/nborder.svg)](https://pypi.org/project/nborder/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## What this catches

| Code  | Name                                | One-line example |
|-------|-------------------------------------|------------------|
| NB101 | Non-monotonic execution counts      | Cell 1 ran with `In [3]:` after cell 0 ran with `In [5]:`. |
| NB102 | Won't survive Restart-and-Run-All   | `print(df)` references a name no cell in the notebook defines. |
| NB201 | Use-before-assign across cells      | Cell 0 uses `df`; `df = ...` only appears in cell 1. |
| NB103 | Stochastic library used without seed | `np.random.rand(3)` runs with no seed call before it. |

Each rule has a docs page under [`docs/rules/`](docs/rules/) explaining the bug class, a bad and good example, and the auto-fix behaviour.

## Quick start

```bash
pip install nborder
nborder check notebook.ipynb
nborder check --fix notebook.ipynb
nborder check --output-format=json notebook.ipynb
```

The `--fix` flag reorders cells topologically when the dependency graph is a DAG, injects library-appropriate seed calls for stochastic libraries, and clears execution counts when they no longer reflect a reproducible run order. Every fix is a pipeline stage with a `bailed` outcome that does not block other fixes; running the same fix twice is a byte-stable no-op.

## Pre-commit

Add this to your `.pre-commit-config.yaml`:

```yaml
repos:
  - repo: https://github.com/moonrunnerkc/nborder
    rev: v0.1.0
    hooks:
      - id: nborder
```

Then `pre-commit install`. Full setup notes in [`docs/integrations/pre-commit.md`](docs/integrations/pre-commit.md).

## GitHub Actions

```yaml
- uses: moonrunnerkc/nborder@v0.1.0
  with:
    path: notebooks/
```

Diagnostics show up as inline annotations on the PR. Full options in [`docs/integrations/github-actions.md`](docs/integrations/github-actions.md).

## Configuration

`nborder` reads its configuration from `[tool.nborder]` in `pyproject.toml`:

```toml
[tool.nborder.seeds]
value = 42
libraries = ["numpy", "torch", "tensorflow", "random"]
```

Run `nborder config` to print the effective merged configuration.

## FAQ

**Why not use ruff?** Ruff lints Python source, not notebook structure. It does not see cross-cell dataflow, so it cannot detect that `df` is used in cell 0 and only defined in cell 1. nborder is purpose-built for the cross-cell story; it is complementary to ruff, not competitive.

**How is this different from nbqa?** `nbqa` runs Python linters against notebook cells one at a time. nborder builds a cross-cell symbol dependency graph and reasons about the relationships between cells, which is the part nbqa explicitly does not do.

**Does it work with R or Julia notebooks?** Not in v0.1. Multi-language support is reserved for a future release. Python kernels cover roughly 95% of notebooks in the wild.

**Will it modify my notebook outputs?** No. Outputs, cell metadata, and notebook-level metadata are read-only. The only fix that touches `execution_count` is a clear-to-null operation that runs as part of the reorder fix.

**What about magics?** `%line`, `%%cell`, `!shell`, and shell-assignment forms (`files = !ls`) are stripped to typed metadata before parsing. Magic-defined bindings (e.g., `%%capture out` defines `out`) are recorded in the dataflow graph; see [`docs/known-limitations.md`](docs/known-limitations.md) for the limits.

**How do I suppress a false positive?** Add `# nborder: noqa` (suppress all rules in the cell) or `# nborder: noqa: NB201,NB102` (suppress specific rules) to any line in the cell.

**What if I want to disable a rule entirely?** Rule selection lands in v0.2. For now, use `# nborder: noqa: NB201` to suppress a rule for one cell.

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md).

## License

MIT. See [`LICENSE`](LICENSE).
