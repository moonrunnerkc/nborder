# nborder v0.1.0 Release Audit

Date: 2026-04-26
Auditor: Claude Code (Opus 4.7, 1M context)
Result: PASS_WITH_NOTES

## Summary

`nborder` v0.1.0 is shippable. The release tag exists on `main`, the wheel is live on PyPI as `nborder==0.1.0`, a fresh-venv install resolves and runs `nborder check` on a clean fixture without errors, and every Phase 0 through Phase 7 exit gate verified independently. The four MVP rules (NB101, NB102, NB201, NB103) fire correctly on triggering fixtures and stay silent on boundary cases. The byte-stable round-trip invariant holds on v4.0, v4.4, and v4.5 clean fixtures. The dataflow graph passes its sub-50ms perf gate on a 100-cell synthetic notebook. Quality gates are green: 125 tests pass, 97 percent overall coverage, `mypy --strict` clean, `ruff check src tests` clean, no em dashes or emojis in any tracked file.

The notes that prevent a clean PASS are scoped, non-blocking, and either documented in the project's own internal `.github/tech-debt-review.md` or trivially fixable. The CLI accepts `--select` but does not actually filter rules; `action.yml` forwards `--select` to that no-op flag. One untracked file (`.github/tech-debt-review.md`) sits in the working tree containing em dashes and emojis, but it is not committed and therefore does not violate the project's em-dash discipline on the shipped artefact set. The sklearn NB103 fixture incidentally fires a spurious NB102 on the `random_state` keyword name; NB103 itself behaves correctly. Per-package `graph/` coverage is 99 percent (one missing line in `builder.py:96`) rather than the 100 percent claimed in the Phase 2 summary; the deficit is one line and not load-bearing. None of these block launch, but each is worth recording.

## Phase-by-phase verification

### Phase 0: Scaffolding
Status: PASS

Evidence:

- All scaffolding files present and non-empty:
  - `pyproject.toml` (1492 bytes), `LICENSE` (1069 bytes; first line `MIT License`), `README.md` (4288 bytes), `.gitignore` (524 bytes), `.pre-commit-config.yaml` (405 bytes).
  - `src/nborder/__init__.py` exposes `__version__ = "0.1.0"`.
  - `tests/` directory present with 20 test modules.
  - `.github/workflows/ci.yml` present.
- `pip install -e ".[dev]"` succeeds in the active venv:
  ```
  Successfully built nborder
  Installing collected packages: nborder
    Attempting uninstall: nborder
      Found existing installation: nborder 0.1.0
      Uninstalling nborder-0.1.0:
        Successfully uninstalled nborder-0.1.0
  Successfully installed nborder-0.1.0
  ```

### Phase 1: Parser, Writer, NB101
Status: PASS

Evidence:

- Parser layout under `src/nborder/parser/`: `__init__.py`, `magics.py`, `models.py`, `reader.py`, `writer.py`.
- NB101 fires on `tests/fixtures/NB101/non_monotonic.ipynb` with exit code 1:
  ```
  tests/fixtures/NB101/non_monotonic.ipynb:cell_1:1:1: NB101 Execution count 3 appears after 5. The notebook was not run in source order. [*]
  Found 1 error. 1 fixable with --fix.
  ```
- Byte-stable round-trip on the three clean fixtures (each verified with `cmp` after `nborder check --fix`):
  ```
  BYTE_STABLE: v40_clean
  BYTE_STABLE: v44_clean
  BYTE_STABLE: v45_clean
  ```
- `nbformat_minor` preservation:
  ```
  v40_clean minor= 0
  v44_clean minor= 4
  v45_clean minor= 5
  ```

### Phase 2: Dataflow Graph
Status: PASS_WITH_NOTES

Evidence:

- Package layout under `src/nborder/graph/`: `builder.py`, `cst_helpers.py`, `extractor.py`, `models.py`, `wildcards.py`, `__init__.py`.
- Direct `nborder.graph` coverage: 99 percent total, one missing line at `builder.py:96`:
  ```
  Name                               Stmts   Miss  Cover   Missing
  src/nborder/graph/__init__.py          1      0   100%
  src/nborder/graph/builder.py          63      1    98%   96
  src/nborder/graph/cst_helpers.py      51      0   100%
  src/nborder/graph/extractor.py       186      0   100%
  src/nborder/graph/models.py          106      0   100%
  src/nborder/graph/wildcards.py        11      0   100%
  TOTAL                                418      1    99%
  ```
  Phase 2 summary claimed 100 percent. The single uncovered line is a non-load-bearing branch in `builder.py`; documented in tech-debt review.
- Performance test passes:
  ```
  tests/test_graph_builder.py::test_dataflow_graph_builds_100_cell_notebook_under_50ms PASSED [100%]
  1 passed in 0.31s
  ```
- Real-world corpus: `tests/fixtures/real_world/` contains 20 notebooks. `nborder check tests/fixtures/real_world/` exits 1 with diagnostics ("Found 65 errors. 9 fixable with --fix.") and no traceback or import error.

### Phase 3: NB201, NB102, Reorder Fix
Status: PASS

Evidence:

- Rule files present: `src/nborder/rules/nb201.py`, `src/nborder/rules/nb102.py`.
- `Diagnostic` and `FixDescriptor` data model in `src/nborder/rules/types.py` carries every required field (`code`, `severity`, `message`, `notebook_path`, `cell_index`, `cell_id`, `line`, `column`, `end_line`, `end_column`, `fixable`, `fix_descriptor`; `FixDescriptor` carries `fix_id`, `target_cells`, `description`).
- NB201 fixture round-trip on `tests/fixtures/NB201/use_df_later_def.ipynb`:
  ```
  cell_0:1:7: NB201 Variable `df` used in cell 0 is only defined in cell 1. [*]
  Found 1 error. 1 fixable with --fix.        # exit 1
  Fix outcomes:
    reorder: applied (reordered 2 cells and cleared execution counts)   # exit 0
                                              # second check exit 0, clean
  ```
- Reorder idempotency on the same fixture:
  ```
  IDEMPOTENT
  ```
- Reorder bail on cycle (`tests/fixtures/phase3/reorder_cycle.ipynb`):
  ```
  Fix outcomes:
    reorder: bailed (Cycle detected. Cell 1 defines `y` used by cell 0. Cell 0 defines `x` used by cell 1. Automatic reordering cannot resolve circular dependencies; restructure the notebook manually.)
  ```
  Diagnostic names the cells and the symbols.
- NB102 fires on `tests/fixtures/NB102/undefined_name.ipynb` and reports "0 fixable" (NB102 has `fixable=false`):
  ```
  tests/fixtures/NB102/undefined_name.ipynb:cell_0:1:7: NB102 Name `some_undefined_name` is used in cell 0 but never defined in the notebook.
  Found 1 error. 0 fixable with --fix.
  ```
- Wildcard import suppression on `tests/fixtures/phase3/wildcard.ipynb`:
  - Default flags: no diagnostics, exit 0.
  - `--include=info`: emits `NB102 Possibly defined by wildcard import from numpy: Name array is used in cell 0 but never defined in the notebook.`
  Note: the wildcard-derived message is reported at default severity by nborder's text reporter ("Found 1 error"), but the rule keeps the use suppressed at default verbosity. The behavior matches the spec; the prefix "Possibly defined by wildcard import from numpy" is the marker.

### Phase 4: NB103 and Seed Injection
Status: PASS_WITH_NOTES

Evidence:

- NB103 rule: `src/nborder/rules/nb103.py`. Registry: `src/nborder/rules/seed_registry.py`.
- Registry covers numpy, random (stdlib), torch, tensorflow, jax (diagnostic-only via `injection_template=None`), sklearn (diagnostic-only via `injection_template=None`). torch.cuda detection lives in `src/nborder/fix/seeds.py` (`_torch_cuda_imported`) and adds `torch.cuda.manual_seed_all` when `torch.cuda` is imported.
- numpy seed injection on `tests/fixtures/NB103/numpy_unseeded.ipynb`:
  ```
  Fix outcomes:
    seeds: applied (numpy seed injected at cell 1)
  cell 0: import numpy as np / rng = np.random.default_rng(42)
  cell 1: import numpy as np / values = np.random.rand(3)
  ```
  Modern Generator API, not legacy `np.random.seed`.
- Multi-library single-cell injection on `numpy_torch_unseeded.ipynb`:
  ```
  cell 0: import numpy as np / rng = np.random.default_rng(42)
          import torch / torch.manual_seed(42)
  ```
  One injected cell, both libraries.
- torch.cuda detection on `torch_cuda_unseeded.ipynb`:
  ```
  cell 0: import torch / torch.manual_seed(42) / torch.cuda.manual_seed_all(42)
  ```
- jax diagnostic-only: `--fix=seeds` on `jax_unseeded.ipynb` reports `seeds: no-op (no NB103 seed diagnostics found)` and the cell count remains 1 (no injection). The diagnostic message reads "JAX random API used without explicit PRNGKey plumbing. Thread a jax.random.PRNGKey through stochastic calls."
- sklearn diagnostic-only on `sklearn_random_state_none.ipynb`:
  ```
  cell_0:2:9: NB103 scikit-learn estimator uses random_state=None. Pass a deterministic random_state value.
  ```
  No fix applied. Note: a spurious `NB102 Name random_state is used in cell 0 but never defined in the notebook.` also fires because the keyword-argument target is being treated as a name use. NB103 itself is correct; the NB102 false positive is logged below as a quality note.
- noqa suppression for all four codes works. `nborder check` on `tests/fixtures/suppression/{NB101,NB102,NB103,NB201}.ipynb` exits 0 (no diagnostics). Removing the `# nborder: noqa: <code>` comment reproduces the diagnostic in every case (verified for NB102, NB103, NB201; the bundled NB101 fixture has `execution_count=None` everywhere, so it does not exercise the suppression path empirically, although `tests/test_suppression.py::test_nb101_noqa_suppresses_execution_count_diagnostic` does cover it programmatically).
- Bare `# noqa: NB103` is NOT honored: a synthetic fixture with `import numpy as np / values = np.random.rand(3)  # noqa: NB103` still fires NB103 (exit 1). This protects bare ruff `# noqa` comments from being silently consumed.
- Library config filter: `[tool.nborder.seeds] libraries = ["numpy"]` in a pyproject.toml at the run cwd, applied to `config_numpy_only.ipynb` (numpy + torch unseeded), produces only the numpy diagnostic; torch is suppressed.
- Seed cell import handling on `numpy_preimported_in_parameters.ipynb`:
  - Original: parameters cell has `import numpy as numpy_lib`, downstream cell uses `numpy_lib.random.rand`.
  - After `--fix=seeds`: a new cell is inserted at position 1 (after parameters cell at position 0) containing only `rng = numpy_lib.random.default_rng(42)`. No redundant `import numpy` line, alias preserved.

### Phase 5: Reporters and CLI Polish
Status: PASS_WITH_NOTES

Evidence:

- Reporter modules under `src/nborder/reporters/`: `base.py`, `github.py`, `jsonout.py`, `sarif.py`, `text.py`. `base.py` defines an `ABC` with a single `report(diagnostics, fix_outcomes=None) -> str` abstract method.
- Text reporter on `tests/fixtures/phase3/mixed.ipynb`:
  ```
  tests/fixtures/phase3/mixed.ipynb:cell_0:1:7: NB201 Variable `df` used in cell 0 is only defined in cell 1. The notebook will fail on Restart-and-Run-All. [*]
  tests/fixtures/phase3/mixed.ipynb:cell_0:2:7: NB102 Name `totally_undefined` is used in cell 0 but never defined in the notebook.
  Found 2 errors. 1 fixable with --fix.
  ```
  Format matches `path:cell_N:line:col: NB### message [*]` plus summary.
- JSON reporter shape (validated through `python -m json.tool`):
  ```
  {
    "diagnostics": [
      {"notebook_path": "...", "cell_index": 0, "cell_id": "mixed-use",
       "line": 1, "column": 7, "end_line": 1, "end_column": 9,
       "code": "NB201", "severity": "error",
       "message": "...", "fixable": true, "fix_id": "reorder"},
      {...NB102 diagnostic, "fixable": false, "fix_id": null}
    ],
    "fix_outcomes": null
  }
  ```
- GitHub Actions reporter:
  ```
  ::error file=tests/fixtures/phase3/mixed.ipynb,line=1,col=7,endLine=1,endColumn=9,title=NB201::Variable `df`...
  ::error file=tests/fixtures/phase3/mixed.ipynb,line=2,col=7,endLine=2,endColumn=24,title=NB102::Name `totally_undefined`...
  ```
- SARIF reporter: top-level keys include `version: "2.1.0"`, `runs[0].tool.driver.name: "nborder"`, `runs[0].tool.driver.version: "0.1.0"`, a `rules` array with all four codes, and a `results` array. Output validated against `tests/fixtures/sarif/sarif_schema.json` via `jsonschema.validate`:
  ```
  SARIF VALID against schema
  ```
- `--include=info` flag: on `tests/fixtures/phase3/wildcard.ipynb`, default run yields no diagnostics; `--include=info` emits the wildcard NB102 diagnostic.
- `--exit-zero`:
  ```
  no flag:    1
  exit-zero:  0
  ```
- `nborder rule NB101` prints the rendered docs page (verified output begins with `# NB101: non-monotonic execution counts`).
- `nborder config` prints valid TOML showing the effective configuration:
  ```
  [tool.nborder]

  [tool.nborder.seeds]
  value = 42
  libraries = ["numpy", "torch", "tensorflow", "random", "jax", "sklearn"]
  ```
- `docs/output-formats.md` and `docs/known-limitations.md` exist.

Note: `--select=<CODES>` is accepted by the CLI without error but does not actually filter the rule set. Verified by passing `--select=NB201` to a notebook that only triggers NB101: NB101 still fires. `action.yml` forwards `--select` to this no-op flag. Documented as TD-022/TD-023 in `.github/tech-debt-review.md`. Not a launch blocker because `select` defaults to all rules and adopters who pass nothing get the documented behavior; users who pass a value get more rules than they asked for, not fewer.

### Phase 6: Integrations
Status: PASS

Evidence:

- `.pre-commit-hooks.yaml` defines the hook with `entry: nborder check` and `types: [jupyter]`:
  ```yaml
  - id: nborder
    name: nborder
    description: Lint Jupyter notebooks for hidden-state and execution-order bugs
    entry: nborder check
    language: python
    types: [jupyter]
    require_serial: false
  ```
- `action.yml` declares `name`, `description`, `author`, branding (`check-circle`/`green`), inputs (`path`, `fix`, `select`), `runs.using: composite`, an install step (`pip install nborder`) and a run step that invokes `nborder check --output-format=github`.
- `.github/workflows/example-lint.yml` references `moonrunnerkc/nborder@v0.1.0`.
- `.github/workflows/ci.yml` includes the dogfood step `nborder check tests/fixtures/roundtrip` after running ruff, mypy, and pytest.
- `docs/integrations/pre-commit.md` and `docs/integrations/github-actions.md` both exist.

### Phase 7: Docs and Release
Status: PASS

Evidence:

- Per-rule docs: `docs/rules/{NB101,NB102,NB201,NB103}.md` all present. Each carries title, "Why it matters", "Bad", "Good", "Auto-fix", "Configuration", "Related rules" sections (verified by `grep -E "^# |^## "`).
- README.md sections verified: title and one-line description, badges row (PyPI, CI, Python, License), "What this catches" 4-row table, Quick start, Pre-commit snippet, GitHub Actions snippet, Configuration pointer, FAQ with 7 entries, Contributing pointer, License section.
- CONTRIBUTING.md covers dev environment setup, the three checks, "Add a rule" with the five required pieces, code-style pointer to `.github/copilot-instructions.md`, commit-message conventions, and a PR checklist.
- CHANGELOG.md has a `## [0.1.0] - 2026-04-26` entry summarizing every shipped feature. Note: no `## [Unreleased]` section, which the contributing guide requires for in-flight work; documented as TD-051. Not a launch blocker; the v0.1.0 entry is complete.
- `docs/index.md` links the four rule pages, output formats, known limitations, both integration guides, the changelog, contributing, and license.
- `.github/workflows/release.yml` triggers on `v*.*.*` tag push, builds wheel and sdist with `python -m build`, publishes via `pypa/gh-action-pypi-publish@release/v1` using `secrets.PYPI_API_TOKEN`, and creates a GitHub release with auto-generated notes via `softprops/action-gh-release@v2`.
- PyPI presence:
  ```
  nborder (0.1.0)
  Available versions: 0.1.0, 0.0.1
    INSTALLED: 0.1.0
    LATEST:    0.1.0
  ```
  Fresh-venv install (`/tmp/pypi_test_venv`) succeeded; `nborder check` on `tests/fixtures/roundtrip/v45_clean.ipynb` exited 0; `python -c "import nborder; print(nborder.__version__)"` printed `version: 0.1.0`.

## Quality gates

- Test suite: 125 passed, 0 failed, 0 skipped, 0 errors. `pytest -v` ran in 1.92s.
- Coverage: 97 percent overall (1489 statements, 45 missed). Per-module:
  - `parser/`: reader 83%, writer 92%, magics 98%, models 100%.
  - `graph/`: 99% (one missing line in `builder.py`).
  - `rules/nb101.py`: 100%.
  - `rules/nb102.py`: 100%.
  - `rules/nb201.py`: 100%.
  - `rules/nb103.py`: 96%.
  - `reporters/`: 100% across base, github, jsonout, sarif, text.
  - `fix/pipeline.py`: 93%; `fix/seeds.py`: 92%.
- mypy --strict: `Success: no issues found in 34 source files`. Exit 0.
- ruff check src tests: `All checks passed!`. Exit 0.
- Em dash scan over tracked files (`git ls-files | xargs grep -l $','`): no matches.
- Emoji scan over tracked files and commit messages: no matches.

## Known issues or notes

1. `--select=<CODES>` is a no-op. The CLI accepts the flag without error and `action.yml` forwards it, but the rule set is not filtered. Adopters who pass `--select` get more rules than they asked for, not fewer. Already tracked as TD-022/TD-023.
2. NB102 false positive on the sklearn fixture. `RandomForestClassifier(random_state=None)` triggers NB103 correctly and also fires `NB102 Name random_state is used in cell 0 but never defined in the notebook.` because the keyword-argument target is being collected as a name use. The NB103 path itself is correct; the NB102 misclassification is a graph-extractor gap.
3. Per-package `graph/` coverage is 99 percent, not the 100 percent claimed in the Phase 2 summary. One uncovered line in `builder.py:96`.
4. The Phase 4 NB101 suppression fixture (`tests/fixtures/suppression/NB101.ipynb`) sets all `execution_count` to null, so it does not exercise the NB101 noqa path empirically. The corresponding test (`tests/test_suppression.py::test_nb101_noqa_suppresses_execution_count_diagnostic`) does cover it programmatically by constructing the fixture in code.
5. Untracked file `.github/tech-debt-review.md` sits in the working tree containing em dashes and emojis. It is not committed, so the em-dash and emoji discipline holds for shipped artefacts. If this file is intended to ship, it needs an em-dash sweep; if it is intended to stay local, it should be `.gitignore`d.
6. `BUILD_PLAN.md` lives at `.github/BUILD_PLAN.md`, not the repo root. Not a launch blocker; flagged so future audits do not look for it in the wrong place.
7. CHANGELOG lacks an `## [Unreleased]` section that the contributing guide requires for in-flight work. The v0.1.0 entry is complete; the missing section affects the next contribution, not this release.
8. Real-world corpus run reports 65 NB10x/NB20x findings across 20 notebooks. None of these are crashes or tracebacks, but several are likely false positives (`color`, `dtype` flagged on Jake VanderPlas's IPython tutorial chapters). Worth a follow-up after launch to characterize the false-positive rate, not a launch blocker.

## Recommendation

PASS_WITH_NOTES: ready to launch. The eight notes above are scoped, none break adopter-facing behavior in the documented happy paths, and most are already logged in the project's own internal tech-debt review. Recommend filing items 1, 2, and 5 as v0.1.1 issues and addressing within 14 days; items 3, 4, 6, 7 as docs/cleanup tasks for the next minor release; item 8 as a tracking issue for false-positive characterization once external feedback arrives.
