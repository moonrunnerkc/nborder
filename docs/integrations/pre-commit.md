# Pre-commit hook

`nborder` ships a pre-commit hook so reproducibility checks run automatically before every commit that touches a Jupyter notebook. The hook calls `nborder check` on the staged `.ipynb` files; if any diagnostic fires, the commit is blocked until you fix or suppress it.

## What this gives you

- Catches `# nborder` violations at commit time, before they reach review or CI.
- Stops broken or non-reproducible notebooks from landing on the main branch.
- Runs only against staged `.ipynb` files, so unrelated notebook changes are untouched.

## Setup

Add this entry to `.pre-commit-config.yaml` in the repo you want to lint:

```yaml
repos:
  - repo: https://github.com/moonrunnerkc/nborder
    rev: v0.1.0
    hooks:
      - id: nborder
```

Then install the hook:

```bash
pip install pre-commit
pre-commit install
```

The next time you `git commit` and a `.ipynb` file is staged, the hook will run `nborder check` on it. To run it on every notebook in the repo (not just staged files):

```bash
pre-commit run nborder --all-files
```

## Configuration

The hook honours your project's `[tool.nborder]` section in `pyproject.toml`. You do not need to repeat configuration in `.pre-commit-config.yaml`.

To pass extra flags through to `nborder`, override the `args` key:

```yaml
- id: nborder
  args: ["--include=info"]
```

## Uninstalling

```bash
pre-commit uninstall
```

This removes the git hook but leaves `.pre-commit-config.yaml` intact, so other developers on the project continue to run the hook.
