# nborder documentation

A fast, opinionated linter and auto-fixer for Jupyter notebook hidden-state and execution-order bugs.

## Rules

- [NB101: non-monotonic execution counts](rules/NB101.md)
- [NB102: won't survive Restart-and-Run-All](rules/NB102.md)
- [NB201: use-before-assign across cells](rules/NB201.md)
- [NB103: stochastic library used without seed](rules/NB103.md)

## CLI and reporters

- [Output formats](output-formats.md): text, JSON, GitHub Actions, SARIF.
- [Known limitations](known-limitations.md): cell-relative line numbers, multi-language kernels, magic-only cells.

## Integrations

- [Pre-commit hook](integrations/pre-commit.md)
- [GitHub Action](integrations/github-actions.md)

## Project

- [Changelog](../CHANGELOG.md)
- [Contributing](../CONTRIBUTING.md)
- [License (MIT)](../LICENSE)
