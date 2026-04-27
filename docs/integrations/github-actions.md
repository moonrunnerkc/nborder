# GitHub Action

The `nborder` GitHub Action runs the linter as a CI step and surfaces diagnostics as inline annotations on the affected notebook cells. Annotations appear in the PR "Files changed" view and in the workflow summary.

## What this gives you

- Inline review comments on the exact cell that fails a rule, scoped to the PR diff.
- A red workflow when a non-reproducible or broken notebook is pushed.
- Optional `--fix` mode that opens a follow-up patch when bots are allowed to commit.

## Setup

Drop this workflow file in `.github/workflows/lint.yml`:

```yaml
name: Lint notebooks

on: [push, pull_request]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - uses: moonrunnerkc/nborder@v0.1.0
        with:
          path: notebooks/
```

That's it. The action installs `nborder` from PyPI, runs `nborder check --output-format=github` against the directory you point at, and exits non-zero if any rule fires.

## Inputs

| Input | Default | Description |
|-------|---------|-------------|
| `path` | `.` | Directory or file to scan. |
| `fix` | `false` | When `true`, runs `nborder check --fix` instead of just checking. |

## Combining with auto-fix

If you want `--fix` to run and have a bot open a follow-up PR with the changes, you can chain `peter-evans/create-pull-request` after this action. That pattern is out of scope for v0.1; the action surface is intentionally minimal.

## Comparison with the pre-commit hook

The pre-commit hook catches problems before commit; the GitHub Action catches problems before merge. They are complementary. Most teams adopt both.
