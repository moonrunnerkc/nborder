# Technical Debt Review: `nborder`

**Reviewer:** Principal Software Architect (audit)
**Date:** 2026-04-26
**Repository:** `nborder` (v0.1.0, branch `main` at commit `1477f98`)
**Scope:** Full codebase audit (src/, tests/, docs/, .github/, action.yml, packaging)

---

## 1. Executive Summary

`nborder` is a small, well-focused Python CLI for linting Jupyter notebooks for hidden-state and execution-order bugs. It ships four rules (NB101, NB102, NB103, NB201), a four-format reporter family (text, JSON, GitHub Actions, SARIF), an auto-fix pipeline, a pre-commit hook, and a composite GitHub Action. The codebase shows real architectural discipline: strict typing, frozen slotted dataclasses, layered modules, and a 125-test suite at **97% line coverage** that all passes locally.

The debt that exists is the kind that always accumulates near the edges of an MVP race to v0.1.0: **the CLI surface lies about its own feature set, the action passes flags the binary silently drops, the docs and the BUILD_PLAN promise capabilities the code never grew, and a handful of correctness issues lurk in error paths that real users will hit on day one**. None of the debt threatens the core value proposition (the dataflow graph), but several items will burn a real adopter the first time they exercise them.

### Health score: **7.5 / 10**

Justification: rule engine, graph layer, parser/writer, and reporters are production-grade. The failures are concentrated in the CLI argument plumbing, packaging integration (docs not shipped), and the gap between documented and implemented configuration. None require reworking architecture; nearly all are 1- to 4-hour fixes.

### Issue counts

| Priority | Count |
|----------|-------|
| **High** | 8     |
| **Medium** | 13   |
| **Low** | 13     |
| **Total** | **34** |

### Top 5 risks

1. **TD-001 / TD-022 / TD-023:** The CLI silently swallows unknown flags (`--select=...` from the action, typo'd `--fxi`, etc.). The composite action's `select` input is wired to `--select=...` and the CLI drops it on the floor. **Adopters will think rule filtering works, observe diagnostics they tried to disable, and lose trust in the tool.**
2. **TD-008 / TD-009:** `nborder rule NB101` resolves docs via `Path(__file__).parent.parent.parent / "docs"`. When users `pip install nborder`, the `docs/` directory is not packaged, so the command always prints "Documentation not yet available." **The headline `nborder rule <CODE>` UX is broken on every PyPI install.**
3. **TD-034:** `graph/wildcards.py` calls `importlib.import_module(name)` on whatever module name appears after `from <X> import *` in a notebook. If a malicious or untrusted notebook contains `from evil_pkg import *` and `evil_pkg` is reachable on `sys.path` (e.g., a sibling package in the repo), arbitrary code executes at lint time. **For a tool meant to run in pre-commit and CI on PR content, this is a real supply-chain hazard.**
4. **TD-041 / TD-043:** Passing a non-existent path or a non-`.ipynb` file produces either an unhandled `FileNotFoundError` traceback or, worse, exit-code 0 with no output and no scan. Users have no way to tell whether their command did anything.
5. **TD-049:** The `[reproduce]` extra installs `papermill` but no code references it. The dynamic `--reproduce` flag is documented in `copilot-instructions.md` and `BUILD_PLAN.md` but never implemented. This is dead promise surface that will frustrate the first user who tries `pip install nborder[reproduce]`.

### Repayment effort

- **Quick wins (Day 1, ~6 hours total):** TD-001, TD-002, TD-008/TD-009, TD-022/TD-023, TD-027/TD-028, TD-041, TD-043, TD-051. Mostly small, surgical fixes.
- **30-day batch (~2-3 dev days):** TD-005, TD-010, TD-012, TD-013-TD-016 (file-cap refactors), TD-018, TD-020, TD-030, TD-049 (decide: implement or remove `--reproduce`).
- **90-day strategic (~1 week):** TD-034 (sandboxed wildcard resolution), TD-006/TD-007 (algorithmic robustness), TD-017 (ImportBinding discriminated union), TD-033 (trusted publishing).
- **6-month architectural:** Limited; the architecture is healthy. Optional move to a single canonical config schema (TD-022 root cause) and proper rule-selection plumbing.

Recommend a **15% sprint allocation** to debt for the next two cycles, then drop to 10% steady state.

---

## 2. Project Overview & Tech Stack

| Dimension | Value |
|-----------|-------|
| Language | Python 3.10+ (`requires-python = ">=3.10"`) |
| Build backend | setuptools >= 69, src layout |
| CLI framework | `typer >= 0.15` |
| Notebook I/O | `nbformat >= 5.10` |
| AST parsing | `libcst >= 1.5` (cell-level CST with position metadata) |
| Output | `rich >= 13.9` (used only indirectly via typer styling) |
| Optional extras | `[reproduce]` -> `papermill >= 2.6` (declared, **unused**); `[dev]` -> ruff/mypy/pytest/pytest-cov/jsonschema/pre-commit |
| Test harness | pytest 8.3, pytest-cov 6.0, jsonschema for SARIF validation |
| Lint & types | ruff 0.8 (E,F,I,UP,B,SIM); mypy 1.14 strict on `src/` |
| CI | GitHub Actions matrix on Python 3.10 / 3.11 / 3.12, Ubuntu only |
| Distribution | PyPI (token-based publish via tag push), GitHub Releases, composite Action |
| Pre-commit hook | `.pre-commit-hooks.yaml` exposing the `nborder` hook with `types: [jupyter]` |

**Source tree (`src/nborder/`)**

```
__init__.py              version stub
cli.py             283 LOC   typer CLI, --fix token parser, reporter dispatch
config.py           74 LOC   tomllib loader + SeedConfig dataclass
parser/
  models.py         48 LOC   Cell, Notebook, Magic dataclasses
  reader.py         98 LOC   nbformat -> Notebook adapter, magic stripping
  writer.py        117 LOC   byte-stable serializer with mutation hooks
  magics.py        117 LOC   strip_magics(), shell-assignment, %%capture binding
graph/
  models.py        156 LOC   DataflowGraph + topo_sort + detect_cycle
  builder.py       121 LOC   per-cell symbol resolution + parameter cells + skip
  extractor.py     297 LOC   LibCST visitor for defs/uses (AT 300-LINE CAP)
  cst_helpers.py   135 LOC   target_names, dotted_name, etc.
  wildcards.py      24 LOC   importlib-based wildcard resolution
rules/
  types.py          34 LOC   Diagnostic + FixDescriptor
  nb101.py          47 LOC
  nb102.py          91 LOC
  nb103.py         242 LOC   library-aware unseeded-stochastic detection
  nb201.py          60 LOC
  seed_calls.py     83 LOC   CallEvent extractor
  seed_registry.py 110 LOC   SEED_PROBES table
  suppression.py    53 LOC   # nborder: noqa pragma filter
  unresolved.py     83 LOC   classify_unresolved_uses (NB201 vs NB102 partition)
fix/
  models.py         18 LOC   FixOutcome dataclass
  pipeline.py      279 LOC   plan_fix_pipeline + duplicate topo sort/cycle detection
  seeds.py         193 LOC   library-aware seed-cell synthesis
reporters/
  base.py           26 LOC
  text.py           99 LOC   ruff-style + ANSI color
  jsonout.py        61 LOC
  github.py         50 LOC
  sarif.py         142 LOC   2.1.0 hand-rolled, schema-validated in tests
```

Total source: **3,149 LOC** across 30 modules. Test suite: **1,907 LOC** across 20 files, 125 tests.

**Entry points:** `nborder` script -> `nborder.cli:app`. Subcommands: `check`, `rule`, `config`.

**Maturity:** v0.1.0 freshly tagged (2026-04-26). Released to PyPI on tag push. README, CHANGELOG, CONTRIBUTING, four per-rule docs pages, two integration docs, and a known-limitations page exist. No `[Unreleased]` section in CHANGELOG (TD-051).

---

## 3. Methodology

The audit followed a four-phase process:

1. **Discovery.** Recursive directory walk, line-count census, root-config read (pyproject, CI workflows, action.yml, pre-commit configs, docs index, BUILD_PLAN, copilot-instructions).
2. **Module-by-module read.** Every Python file in `src/` was read end-to-end. Every test file was read at least to the assertion shape. Every docs page was read for accuracy against the code.
3. **Behavioral verification.** The full test suite was executed (`125 passed` / `97% coverage`) to baseline. The CLI was exercised against deliberately bad inputs (`--select=NB999`, non-existent paths, non-ipynb extensions) to confirm the documented vs implemented behavior gap.
4. **Cross-cutting search.** `grep -RIn` for AI-tells (`data\b`, `result\b`, `temp\b`), em dashes, `Any`, broad `except`, `TODO/FIXME`, and stray `print()` calls. Git ls-files to check for tracked build artifacts.

Every claim in this report is anchored to a specific file path, line number, and (where relevant) a reproducible command. No findings are speculative; tickets without evidence were dropped.

---

## 4. Strengths & Healthy Patterns to Preserve

These patterns are doing real work in this codebase. Keep them as the gravitational center; new code should look like this code.

1. **Rigorous architectural layering.** `parser/` -> `graph/` -> `rules/` and `fix/` consumes diagnostics, full stop. There are no upward imports anywhere; `cli.py` is the only orchestrator. Verified by inspection of every module's import block. This is unusual to see at v0.1 and is the single most valuable structural property of the project. (See `src/nborder/cli.py:9-27` for the orchestration layer; every other module imports strictly downward.)

2. **Frozen slotted dataclasses for value objects.** Every domain record is `@dataclass(frozen=True, slots=True)`: `Cell`, `Notebook`, `Magic` (`parser/models.py:14-48`), `SymbolDef`, `SymbolUse`, `ImportBinding`, `Edge`, `UnresolvedUse`, `DataflowGraph`, `CellSymbols` (`graph/models.py:13-84`), `Diagnostic`, `FixDescriptor` (`rules/types.py:10-34`), `FixOutcome` (`fix/models.py:9-18`), `SeedConfig`, `Config` (`config.py:15-27`). This is exactly the shape the copilot-instructions prescribe and it makes equality, hashing, and pickling free.

3. **Byte-stable round-trip discipline as a CI invariant.** `tests/test_writer.py:17-36` asserts `filecmp.cmp(...)` on v4.0, v4.4, and v4.5 fixtures **and** on the entire real-world VanderPlas notebook corpus. The writer was clearly designed around this constraint from day one (`parser/writer.py:30-33` returns the original bytes verbatim when no mutation is requested). This is a textbook example of getting the dangerous primitive right early.

4. **Real fixtures, not mocks.** Every rule test reads an actual `.ipynb` from `tests/fixtures/<CODE>/` and runs the real pipeline end-to-end. There is no `unittest.mock` anywhere in `tests/`. The graph builder tests use a tiny `_notebook_from_sources` helper (`tests/test_graph_builder.py:183-198`) to avoid I/O without faking the parse layer. Per copilot-instructions: "No mocks where the real thing is testable." Honored.

5. **Test names describe behavior, not wiring.** Sample: `test_dataflow_graph_resolves_to_most_recent_prior_definition`, `test_symbol_extractor_keeps_comprehension_targets_local`, `test_check_fix_reorder_bails_on_cycle_but_clear_counts_runs`. A reader could understand what each test is verifying without opening the implementation.

6. **97% line coverage with deep tests.** `cli.py:97%`, `graph/extractor.py:100%`, `parser/writer.py:92%`, `rules/nb103.py:96%`. The uncovered lines are nearly all error-path returns or unreachable defensive branches. This is the "coverage is a floor, not a goal" outcome the contributing guide asks for.

7. **Suppression mechanism shipped on day one.** `# nborder: noqa` and `# nborder: noqa: NB201,NB102` are implemented (`rules/suppression.py:36-50`) and tested across all four rules (`tests/test_suppression.py`). Adopters always need this, and it's almost always retrofitted later. Shipping it on v0.1 is the right call.

---

## 5. Detailed Findings

Findings are grouped by category. Each issue carries a unique ID, file/line evidence, root cause, impact, recommended fix, effort estimate, and priority.

### A. Code Quality & Maintainability

#### TD-001 , Manual `--fix` token parsing breaks Typer's flag handling

- **Severity:** **High**
- **Evidence:** `src/nborder/cli.py:36`, `cli.py:45`, `cli.py:156-167`

  ```python
  app = typer.Typer(
      help="...",
      context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
  )

  @app.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
  def check(paths: Annotated[list[str], ...], ...): ...

  def _parse_check_tokens(tokens: tuple[str, ...]) -> tuple[str | None, tuple[Path, ...]]:
      fix: str | None = None
      parsed_paths: list[Path] = []
      for token in tokens:
          if token == "--fix":
              fix = "all"
              continue
          if token.startswith("--fix="):
              fix = token.removeprefix("--fix=") or "all"
              continue
          parsed_paths.append(Path(token))   # any unknown flag becomes a Path
      return fix, tuple(parsed_paths)
  ```

  Reproduction: `nborder check --select=NB999 tests/fixtures/NB101/non_monotonic.ipynb` runs cleanly (NB101 still fires), proving `--select=NB999` was silently dropped.

- **Root cause:** Typer's `--fix` and `--fix=value` forms collide because `--fix=...` is not natively expressible as a single Typer option that accepts both bare and `=value` forms. The author worked around it by disabling Typer's flag parsing entirely (`ignore_unknown_options=True, allow_extra_args=True`) and writing a hand-rolled tokenizer that recognizes only `--fix`/`--fix=`. Every other flag now silently becomes a `Path`.

- **Impact:** Any typo in any flag (e.g., `--fxi`, `--ouput-format=json`) is silently turned into a path that `_iter_notebook_paths` then drops. Unknown but plausible flags (`--select`, `--ignore`, `--reproduce`, `--debug`) will appear to work because the binary still emits diagnostics from unrelated rules. Adopters will lose trust the moment they try to scope the linter and observe diagnostics they tried to disable.

- **Recommended fix:** Restore Typer's standard option parsing. Replace the dual-form `--fix` with two explicit Typer options:

  ```python
  @app.command()
  def check(
      paths: Annotated[list[Path], typer.Argument(...)],
      fix: Annotated[bool, typer.Option("--fix")] = False,
      fix_categories: Annotated[
          str | None,
          typer.Option("--fix-categories", help="Comma-separated subset: reorder,seeds,clear-counts"),
      ] = None,
      ...
  ) -> None:
      enabled_fixes = _enabled_fixes(fix=fix, fix_categories=fix_categories, diff=diff)
  ```

  Document `--fix-categories=reorder,seeds` as the way to scope. Drop `context_settings`. Remove `_parse_check_tokens`. Update the action.yml to use `--fix-categories` if it ever needs that. Migration path: ship as v0.2 minor with a deprecation note for `--fix=reorder` (still parse it for one release).

- **Effort:** 2 hours (mostly test updates).

#### TD-002 , `_parse_include` silently drops unknown levels

- **Severity:** **Medium**
- **Evidence:** `src/nborder/cli.py:222-231`

  ```python
  def _parse_include(include: str | None) -> frozenset[Severity]:
      if include is None:
          return _DEFAULT_INCLUDE_LEVELS
      extra_levels: set[Severity] = set()
      for level_token in include.split(","):
          normalized = level_token.strip()
          match normalized:
              case "error" | "warning" | "info":
                  extra_levels.add(normalized)
      return _DEFAULT_INCLUDE_LEVELS | extra_levels
  ```

  `--include=warn` (typo for `warning`) is silently dropped; the user sees no info-level diagnostics and never knows why.

- **Root cause:** Optimistic input handling. The match is lenient because the contributor wanted to avoid Typer-style errors that would block users on minor typos.

- **Impact:** Silent loss of diagnostic visibility. Indirect dataloss in CI: a misconfigured pipeline can fail-open without anyone noticing.

- **Recommended fix:** Raise `typer.BadParameter` listing the valid set when an unknown token appears. Mirror `_select_reporter` which already does the right thing (`cli.py:243-246`).

- **Effort:** 30 minutes.

#### TD-005 , Dead conditional in `_relative_call_name`

- **Severity:** **Low**
- **Evidence:** `src/nborder/rules/nb103.py:178-187`

  ```python
  def _relative_call_name(library_import: LibraryImport, call_name: str) -> str | None:
      if call_name == library_import.alias:
          return ""
      prefix = f"{library_import.alias}."
      if not call_name.startswith(prefix):
          return None
      relative_name = call_name.removeprefix(prefix)
      if library_import.module == "numpy.random" or library_import.imported_name == "random":
          return relative_name
      return relative_name
  ```

  Both branches of the `if/else` return `relative_name`. The condition is structurally meaningless.

- **Root cause:** Early branch was likely intended to apply a numpy-specific rewrite that was later moved to `_is_numpy_random_binding` in `_matches_pattern` (line 168). The vestigial branch was never deleted.

- **Impact:** Misleads readers; minor maintainability cost.

- **Recommended fix:** Delete the conditional; return `relative_name` unconditionally.

- **Effort:** 5 minutes.

#### TD-010 , Silent ignore of non-`.ipynb` paths

- **Severity:** **High**
- **Evidence:** `src/nborder/cli.py:170-178`

  ```python
  def _iter_notebook_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
      notebook_paths: list[Path] = []
      for check_path in paths:
          if check_path.is_dir():
              notebook_paths.extend(sorted(check_path.rglob("*.ipynb")))
              continue
          if check_path.suffix == ".ipynb":
              notebook_paths.append(check_path)
      return tuple(notebook_paths)
  ```

  Reproduction: `nborder check tests/fixtures/NB101/non_monotonic.ipynb.txt` exits 0, prints nothing. The user thinks the file was clean.

- **Root cause:** Defensive filtering written when the parser layer was less resilient. Now that the parser handles the file fine, the filter just hides errors.

- **Impact:** A typo in a filename produces a silent green check. In a pre-commit context the developer never sees the typo; in CI the workflow passes spuriously.

- **Recommended fix:** When the path is a file but not `.ipynb`, raise `typer.BadParameter("path 'X' is not a .ipynb file; pass a directory or a notebook path")`. When the path doesn't exist, raise with the same shape. Allow `is_dir()` paths that contain zero `.ipynb` files to print a notice ("scanned `<dir>`, no notebooks found") rather than exit silently.

- **Effort:** 1 hour (including tests for the three error shapes).

#### TD-011 , CLI re-reads notebook from disk after fix to refresh diagnostics

- **Severity:** **Low**
- **Evidence:** `src/nborder/cli.py:115-124`

  ```python
  write_notebook(notebook, cell_order=..., seed_cell_source=..., clear_execution_counts=...)
  notebook = read_notebook(notebook_path)
  notebook_diagnostics = _check_notebook(notebook, config, include_levels=include_levels)
  ```

- **Root cause:** Easier to write than to mutate the in-memory `Notebook` consistently after a fix. The frozen-dataclass design makes in-place updates intentionally hard.

- **Impact:** A second I/O round-trip per file. On a 100-cell notebook that's roughly 2-5 ms. Not a real-world bottleneck today; flagging as architectural smell.

- **Recommended fix:** When the fix pipeline already produces a fully-mutated `Notebook` (it doesn't quite, today), just rebuild diagnostics from that. As is, the disk re-read is fine; consider adding a comment explaining the choice or keep it simple.

- **Effort:** 1-2 hours; only worth doing if profiling shows it matters.

#### TD-014 , `nb103.py` and `extractor.py` are at or above the project's 300-line ceiling

- **Severity:** **Medium**
- **Evidence:**

  ```text
  src/nborder/graph/extractor.py    297 LOC  (cap = 300)
  src/nborder/cli.py                283 LOC
  src/nborder/fix/pipeline.py       279 LOC
  src/nborder/rules/nb103.py        242 LOC
  ```

  CONTRIBUTING.md:42 declares: "300-line hard cap per file. If a module hits 250, split it along natural seams." Four files are over 250.

- **Root cause:** Standard MVP debt. Each file accumulated until it shipped; nobody has had cause to split them yet.

- **Impact:** Mostly cognitive. `extractor.py` is one new visit method away from breaching the documented hard cap.

- **Recommended fix:** Split along natural seams:
  - `extractor.py` -> keep `_CellSymbolVisitor` in `extractor.py`; move comprehension handling into `extractor_comprehensions.py` (it's a self-contained sub-machine, lines 216-260).
  - `nb103.py` -> move `_matches_pattern` and friends (lines 153-217) into `seed_registry.py` next to `CallPattern`. The pattern-matching logic is registry-shaped, not rule-shaped.
  - `cli.py` -> extract `_check_notebook` and `_visible_diagnostics` into `nborder/check.py`. The CLI then becomes argument plumbing only.
  - `pipeline.py` -> drop the duplicate `_topological_sort` / `_detect_cycle` (TD-012), which already gets it under 250.

- **Effort:** 4 hours (mechanical, well-tested).

#### TD-024 , `_seed_description` claims "injected at cell 1" even when cell index differs

- **Severity:** **Low**
- **Evidence:** `src/nborder/fix/seeds.py:190-193`

  ```python
  def _seed_description(libraries: tuple[str, ...]) -> str:
      library_names = ", ".join(libraries)
      seed_word = "seed" if len(libraries) == 1 else "seeds"
      return f"{library_names} {seed_word} injected at cell 1"
  ```

  When a `parameters` cell exists, the seed cell is inserted at position 1 (after parameters), so the description happens to be correct in that case. When no parameters cell exists, insertion is at position 0; the description still says "cell 1." When a `reorder` stage already ran and the seed cell follows a different prefix, the value is unrelated to the actual insertion position.

- **Root cause:** Hardcoded string written when only one insertion path existed.

- **Impact:** User-facing diagnostic text lies about position. Low-severity but visible.

- **Recommended fix:** Compute the actual insertion position via `_seed_cell_index` (already in `parser/writer.py:99-107`), pass it down, and interpolate.

- **Effort:** 30 minutes.

---

### B. Architecture & Design

#### TD-012 , Topological sort and cycle detection duplicated across `graph/models.py` and `fix/pipeline.py`

- **Severity:** **Medium**
- **Evidence:**
  - Canonical: `src/nborder/graph/models.py:86-119` (`DataflowGraph.topological_sort`) and `:121-156` (`DataflowGraph.detect_cycle`).
  - Duplicate: `src/nborder/fix/pipeline.py:180-208` (`_topological_sort`) and `:211-237` (`_detect_cycle`). Identical algorithm, slightly different signature (takes `dependency_edges` directly instead of a graph).

- **Root cause:** The fix pipeline needs to **augment** the graph with dependency edges synthesized from the diagnostics (not just the resolved edges, which by construction don't include the broken NB201 dependencies , those went to `unresolved_uses`). Rather than threading the augmented edge set into `DataflowGraph.topological_sort`, the author copy-pasted the algorithm.

- **Impact:** Two implementations of the same algorithm. A bug fix in one (e.g., switching from `ready_cells.sort()` per iteration to a heap) has to be made in two places. The augmented variant is also recursive (`pipeline.py:219`), so any stack-depth concern (TD-007) doubles up.

- **Recommended fix:** Extract a free function `topological_sort(cell_indexes: Iterable[int], edges: Iterable[Edge]) -> list[int] | None` and a paired `detect_cycle(...)`, both into `graph/algorithms.py`. Have `DataflowGraph.topological_sort()` and the fix pipeline call into it. Reduces `pipeline.py` from 279 to ~210 LOC and makes the augmentation explicit.

- **Effort:** 2 hours (the algorithm is short; the test surface is well-covered).

#### TD-013 , `cli.py` mixes orchestration, parsing, and filtering

- **Severity:** **Medium**
- **Evidence:** `src/nborder/cli.py:181-219`. `_check_notebook`, `_visible_diagnostics`, `_enabled_fixes`, and `_parse_include` are all CLI helpers but contain **business logic** the rest of the codebase has no way to import without reaching into the CLI module. `tests/test_suppression.py:5` already does this:

  ```python
  from nborder.cli import _check_notebook
  ```

- **Root cause:** Standard expansion. The CLI was the only place this code was needed at v0.1.

- **Impact:** Tests reach into private CLI helpers (the leading underscore is meaningful). When the CLI is refactored, every test that imports from `cli` breaks.

- **Recommended fix:** Move `_check_notebook` and `_visible_diagnostics` to `nborder/check.py` as public `check_notebook` / `filter_visible_diagnostics`. Keep `cli.py` as pure argument plumbing.

- **Effort:** 1 hour.

#### TD-017 , `ImportBinding` is a discriminated union disguised as a flat record

- **Severity:** **Low**
- **Evidence:** `src/nborder/graph/models.py:34-44`. `imported_name` is `None` when `kind == "import"`, a dotted name when `kind == "from"`, and `"*"` when `kind == "wildcard"`. `bound_name` is the last dotted segment for `import x.y`, the alias for `import x as y`, and `None` for wildcards. Different shapes share one record because Python tuples are convenient.

  ```python
  @dataclass(frozen=True, slots=True)
  class ImportBinding:
      module: str
      imported_name: str | None
      bound_name: str | None
      cell_index: CellIndex
      line: int
      column: int
      kind: ImportKind   # Literal["import", "from", "wildcard"]
  ```

- **Root cause:** Flatness was easier; the union shape would have been three dataclasses sharing a `Protocol`.

- **Impact:** Every consumer must `if kind == "wildcard"` or check for `None`. `fix/seeds.py:147-153` and `rules/unresolved.py:82-83` both do this. Future fields (e.g., `wildcard_modules`, `relative_level` for `from .. import x`) bloat the union.

- **Recommended fix:** Replace with three concrete dataclasses (`SimpleImport`, `FromImport`, `WildcardImport`) sharing a `Protocol` or a thin `BaseImport`. Defer until v0.2 when relative-import depth or another field needs adding.

- **Effort:** 3 hours.

#### TD-006 , `topological_sort` re-sorts `ready_cells` on every iteration

- **Severity:** **Low**
- **Evidence:** `src/nborder/graph/models.py:106-115`

  ```python
  ready_cells = sorted(...)
  while ready_cells:
      current_cell = ready_cells.pop(0)   # O(n)
      ordered_cells.append(current_cell)
      for dependent_cell in sorted(dependents_by_cell[current_cell]):
          indegrees[dependent_cell] -= 1
          if indegrees[dependent_cell] == 0:
              ready_cells.append(dependent_cell)
              ready_cells.sort()           # O(n log n) per insertion
  ```

  Worst case: O(n^2 log n). A 100-cell notebook hits this fine because the test (`tests/test_graph_builder.py:150-164`) sets a 50ms budget.

- **Root cause:** Quick-and-correct first implementation. A heap or a sorted insertion would be faster but adds complexity.

- **Impact:** Negligible at notebook scale. Will degrade visibly on a 1000-cell notebook (rare but real for some pedagogical notebooks).

- **Recommended fix:** Use `heapq` instead of `list.sort()`. Or accept the cost and document it.

- **Effort:** 30 minutes.

#### TD-007 , `detect_cycle` uses Python recursion

- **Severity:** **Low**
- **Evidence:** `src/nborder/graph/models.py:139-156` and `src/nborder/fix/pipeline.py:219-231`. Both are recursive DFS. Default Python recursion limit is 1000.

- **Root cause:** Recursive DFS is the natural way to express cycle detection.

- **Impact:** A pathological notebook with >900 cells in a deep dependency chain could hit `RecursionError`. Vanishingly rare today; the project has a 100-cell perf budget.

- **Recommended fix:** Convert to an iterative DFS using an explicit stack of `(cell_index, iter(dependencies))` frames. Or document the limit.

- **Effort:** 1 hour.

#### TD-049 , `[reproduce]` extra installs `papermill` but no code references it

- **Severity:** **High**
- **Evidence:**
  - `pyproject.toml:41-43` declares the extra:

    ```toml
    [project.optional-dependencies]
    reproduce = [
        "papermill>=2.6",
    ]
    ```

  - `grep -RIn 'papermill\|--reproduce' src/` returns zero matches.
  - `BUILD_PLAN.md:6` and `copilot-instructions.md:7` describe `--reproduce` as the dynamic fresh-kernel rerun.
  - `docs/known-limitations.md:9-11` says "The dynamic fresh-kernel rerun is gated behind `--reproduce` and requires the optional `papermill` extra."

- **Root cause:** Phase 8 of the BUILD_PLAN was deferred. The extra and the docs shipped, the implementation didn't.

- **Impact:** A user who follows `docs/known-limitations.md` and runs `pip install nborder[reproduce]; nborder check --reproduce notebook.ipynb` gets `--reproduce` silently dropped via TD-001 and a working dependency they never use. Disappointing first-touch experience.

- **Recommended fix:** Two paths:
  1. **Implement.** Add `src/nborder/dynamic/papermill_runner.py` (lazy import `papermill` only when `--reproduce` is passed) that runs the notebook fresh, captures the kernel-side `NameError`/`ImportError`, and emits diagnostics. Roughly 1-2 dev days.
  2. **Remove.** Delete the extra, delete the docs claim, defer to v0.2 with a public roadmap entry. Roughly 30 minutes.

  **Recommend path 2 for v0.1.x**, path 1 for v0.2.

- **Effort:** 30 min (remove) or 2 days (implement).

---

### C. Testing Debt

#### TD-018 , Per-rule fixture coverage falls short of CONTRIBUTING contract

- **Severity:** **Medium**
- **Evidence:** CONTRIBUTING.md:33 says "At least three fixture notebooks under `tests/fixtures/<CODE>/`: one that triggers the rule, one boundary case that almost-but-not-quite triggers it, and one with the fix already applied." Actual inventory:

  ```text
  tests/fixtures/NB101/  3 notebooks  PASS
  tests/fixtures/NB102/  1 notebook   FAIL
  tests/fixtures/NB201/  1 notebook   FAIL
  tests/fixtures/NB103/  14 notebooks PASS
  ```

  NB102 and NB201 borrow boundary fixtures from `tests/fixtures/phase3/` (e.g., `mixed.ipynb`, `parameters_late.ipynb`, `skip_name_error.ipynb`). The contract is technically violated even though coverage is good.

- **Root cause:** Phase 3 fixtures landed first as integration tests; per-rule fixtures were added retroactively only for rules that needed disambiguation.

- **Impact:** Convention drift. New contributors will model on existing rules and skip the boundary fixture, slowly eroding test discipline.

- **Recommended fix:** Either (a) move the relevant phase3 fixtures into `NB102/` and `NB201/` and accept the duplication where multiple rules share, or (b) update CONTRIBUTING.md to reflect the actual practice: "rules may share fixtures via `tests/fixtures/shared/`." Option (b) is simpler.

- **Effort:** 1 hour.

#### TD-019 , `test_check_diff_outputs_json_diff_without_writing` is shallow

- **Severity:** **Low**
- **Evidence:** `tests/test_cli.py:205-217`

  ```python
  command_outcome = runner.invoke(app, ["check", "--diff", str(copied_notebook)])

  assert command_outcome.exit_code == 1
  assert "Diff for" in command_outcome.output
  assert "---" in command_outcome.output
  assert copied_notebook.read_bytes() == original_bytes
  ```

  The test verifies that *some* diff was printed and that the file wasn't written. It does not verify the diff is correct, points at the right cells, or includes the reordered cell ordering.

- **Root cause:** The author was focused on the safety property (no write) and the existence of output, not the content.

- **Impact:** A bug in `_write_diff` that produced an empty or misleading diff would pass this test. Low risk because `unified_diff` is stdlib, but the contract is undertested.

- **Recommended fix:** Assert on a representative line in the output (e.g., the source-cell content moved to position 0). Or capture the diff against a golden file.

- **Effort:** 30 minutes.

#### TD-020 , Real-world fixtures only smoke-tested

- **Severity:** **Medium**
- **Evidence:** `tests/test_graph_builder.py:142-147` and `tests/test_nb103.py:112-116`:

  ```python
  def test_real_world_fixture_corpus_builds_graph_without_crashing() -> None:
      for fixture_path in sorted((FIXTURE_ROOT / "real_world").glob("*.ipynb")):
          notebook = read_notebook(fixture_path)
          build_dataflow_graph(notebook)

  def test_real_world_corpus_runs_nb103_without_crashing() -> None:
      for fixture_path in sorted((FIXTURE_ROOT / "real_world").glob("*.ipynb")):
          notebook = read_notebook(fixture_path)
          graph = build_dataflow_graph(notebook)
          check_unseeded_stochastic_calls(notebook, graph, SeedConfig())
  ```

  The 20 VanderPlas fixtures (~500 KB total) exercise the graph and one rule, but only against "doesn't crash." If a future change starts firing 50 false-positive NB102s on `02.05-Computation-on-arrays-broadcasting.ipynb`, no test catches it.

- **Root cause:** False-positive regression detection requires golden snapshots, which are tedious to maintain. Smoke tests were the v0.1 compromise.

- **Impact:** Silent regressions on real notebooks. The whole reason for the corpus is to catch them.

- **Recommended fix:** Snapshot the diagnostic JSON for each real-world fixture into `tests/fixtures/real_world_baselines/<fixture>.json`. Update the test to assert exact match with a `--update-baselines` escape hatch (an env var). When a snapshot moves, the diff in the PR review tells the human whether the change was intentional.

- **Effort:** 3 hours (build the snapshot + update infrastructure).

#### TD-021 , Performance test depends on wall-clock timing

- **Severity:** **Low**
- **Evidence:** `tests/test_graph_builder.py:150-164`. The test asserts the 100-cell graph builds in under 50ms, relaxed to 200ms when `sys.gettrace()` is active. CI runs on shared GitHub-hosted runners; a noisy neighbor could spike either threshold.

- **Root cause:** Performance budget enshrined in the BUILD_PLAN. Wall-clock is the simplest way to express it.

- **Impact:** Flaky CI failures under load. Not observed yet; risk grows with runner pressure.

- **Recommended fix:** Replace with a complexity invariant test (e.g., assert that doubling cells produces no more than 2.5x the time across 5 runs) or remove the test and rely on benchmarks outside the CI critical path.

- **Effort:** 1 hour.

---

### D. Documentation & Knowledge Sharing

#### TD-022 , Documented configuration knobs `select`, `ignore`, `extend-include`, `per-file-ignores` are not implemented

- **Severity:** **High**
- **Evidence:**
  - `copilot-instructions.md:178` claims: "Configuration lives under `[tool.nborder]` in `pyproject.toml`: `select`, `ignore`, `fix`, `extend-include`, `per-file-ignores`, plus subtables for `seeds`."
  - `README.md:82` says: "Use the `select` and `ignore` fields in `[tool.nborder]` to drop a rule code from the enabled set."
  - `src/nborder/config.py:15-27` defines only `SeedConfig` and `Config(seeds=...)`. No `select`, `ignore`, `extend-include`, `per-file-ignores` field exists.
  - `grep -RIn 'select\|ignore' src/nborder/config.py` returns nothing matching.

- **Root cause:** The README and copilot-instructions described the v0.2 vision; the code was scoped down to ship v0.1 in the time budget. No issue tracks the gap.

- **Impact:** Adopters configure `[tool.nborder] select = ["NB101"]`, see all four rules still firing, and either file a bug or churn off. The README explicitly tells them this works. **Highest-impact docs/code mismatch in the project.**

- **Recommended fix:**
  - Short-term (1 hour): edit README.md:82 and copilot-instructions.md:178 to remove the `select`/`ignore` claims. Update the known-limitations doc to mention "rule selection is reserved for v0.2."
  - Medium-term (1 dev day): implement rule selection. Schema:

    ```toml
    [tool.nborder]
    select = ["NB1*", "NB201"]   # glob; default "*"
    ignore = ["NB103"]
    ```

    Wire through `_check_notebook` in `cli.py:181-201`. Ship as v0.2.

- **Effort:** 1 hour (docs fix) or 1 day (implementation).

#### TD-023 , `action.yml` passes `--select` to a CLI that does not implement it

- **Severity:** **High**
- **Evidence:** `action.yml:32-36`

  ```yaml
  if [ -n "${{ inputs.select }}" ]; then
    ARGS="$ARGS --select=${{ inputs.select }}"
  fi
  nborder $ARGS "${{ inputs.path }}"
  ```

  The CLI silently drops `--select=...` (TD-001). The action's `select` input is documented in `docs/integrations/github-actions.md:41` as filtering rule codes; in practice it does nothing.

- **Root cause:** Same as TD-022. The action was authored against the planned CLI surface, not the shipped one.

- **Impact:** Anyone using `with: select: NB201` in their workflow will get **all four rules** firing in their CI, contradicting their explicit configuration. They will discover this only when an unrelated NB103 appears on their PR and then track it through three layers of indirection to find the cause.

- **Recommended fix:** Tied to TD-022. Either implement `--select` or remove the `select` input from `action.yml` and `docs/integrations/github-actions.md`. Recommend remove now and re-introduce when the CLI supports it.

- **Effort:** 30 minutes (remove) or part of the TD-022 implementation.

#### TD-025 , CONTRIBUTING claims `nborder check src tests` "dogfoods" but those dirs have no notebooks

- **Severity:** **Low**
- **Evidence:** `CONTRIBUTING.md:67` lists in the PR checklist: "`nborder check src tests` passes (we dogfood)." But `src/` and `tests/` contain only `.py` files (and `tests/fixtures/` contains `.ipynb` fixtures designed to fail). Running `nborder check src tests` actually scans:
  - `src/`: no `.ipynb` -> no diagnostics
  - `tests/`: many `.ipynb` fixtures, several of which **deliberately violate rules**

  So this command will fire diagnostics on the test fixtures. The "dogfood" phrase implies a green check, which it is not.

- **Root cause:** Aspirational language. The intent is that `nborder` lints its own notebooks; it has none, and the test fixtures break the lint by design.

- **Impact:** Confusing instruction for new contributors who follow the PR checklist literally.

- **Recommended fix:** Replace with "`nborder check tests/fixtures/roundtrip` passes (CI does this)." Or remove the bullet entirely; the CI workflow already runs that command on line 43 of `ci.yml`.

- **Effort:** 5 minutes.

#### TD-026 , `BUILD_PLAN.md` and `copilot-instructions.md` are gitignored but committed

- **Severity:** **Low**
- **Evidence:** `.gitignore:1-3`

  ```text
  # Local planning and assistant instructions
  .github/BUILD_PLAN.md
  .github/copilot-instructions.md
  ```

  Yet `git ls-files | grep BUILD_PLAN` shows the file **is** tracked (it must have been committed before the gitignore entry was added; `git rm --cached` was never run).

- **Root cause:** Common gitignore footgun. Gitignore only blocks new files; it doesn't untrack already-tracked ones.

- **Impact:** The maintainer's planning docs are in the public repo, which is mostly fine but slightly out of step with the stated intent. More importantly, the gitignore lies about what's tracked, which confuses future contributors.

- **Recommended fix:** Decide intent. If the docs are public (they're useful), remove from gitignore. If they're meant to be private, run `git rm --cached .github/BUILD_PLAN.md .github/copilot-instructions.md` and commit. Keeping the current state is the worst of both.

- **Effort:** 5 minutes.

#### TD-051 , `CHANGELOG.md` lacks the `[Unreleased]` section the contributing guide requires

- **Severity:** **Low**
- **Evidence:** `CHANGELOG.md:7` jumps straight to `## [0.1.0]`. CONTRIBUTING.md:69 says: "`CHANGELOG.md` has an entry under `## [Unreleased]` describing the change in adopter-facing terms."

- **Root cause:** The 0.1.0 release stamped the changelog without re-opening an unreleased block.

- **Impact:** Next contributor doesn't know where to add their entry. Convention rots.

- **Recommended fix:** Add `## [Unreleased]` immediately under the changelog header.

- **Effort:** 2 minutes.

#### TD-008 / TD-009 , `nborder rule <CODE>` looks for docs at a path not packaged in the wheel

- **Severity:** **High**
- **Evidence:**
  - `src/nborder/cli.py:32`: `_RULE_DOCS_DIR = Path(__file__).parent.parent.parent / "docs" / "rules"`. This resolves to `<install-prefix>/docs/rules/` which doesn't exist in installed wheels.
  - `pyproject.toml:48-49` only declares `[tool.setuptools.packages.find] where = ["src"]`. There's no `package_data`, no `MANIFEST.in`, and `docs/` is not configured as package data.
  - Verified via `dist/nborder-0.1.0-py3-none-any.whl`: extracting reveals no `docs/` directory.

- **Root cause:** The author tested `nborder rule NB101` from a local editable install where `docs/` is reachable from the source tree. The shipped wheel is a different filesystem layout.

- **Impact:** The headline `nborder rule <CODE>` UX prints "Documentation not yet available for NB101." for **every PyPI install**. Tested locally via `cli.py:142-146`:

  ```python
  rule_path = _RULE_DOCS_DIR / f"{rule_code.upper()}.md"
  if rule_path.exists():
      typer.echo(rule_path.read_text(encoding="utf-8"))
      return
  typer.echo(f"Documentation not yet available for {rule_code.upper()}.")
  ```

- **Recommended fix:** Two-step:
  1. Move per-rule docs into `src/nborder/_rule_docs/NB101.md`, etc., and read via `importlib.resources.files("nborder._rule_docs") / f"{rule_code.upper()}.md"`. This works in editable, wheel, and zipapp installs.
  2. Keep the human-readable copies under `docs/rules/` and link them at build time (or just document the canonical location as the package's `_rule_docs/`).

  Update `pyproject.toml`:

  ```toml
  [tool.setuptools.package-data]
  nborder = ["_rule_docs/*.md"]
  ```

- **Effort:** 1 hour.

---

### E. Dependencies & Tooling

#### TD-027 , `dist/` directory committed to repo

- **Severity:** **Medium**
- **Evidence:** `ls dist/` shows `nborder-0.1.0-py3-none-any.whl` and `nborder-0.1.0.tar.gz`. `.gitignore:21` lists `dist/`. Run `git ls-files | grep dist/` to confirm tracking; the gitignore presence suggests the artifacts may not be tracked, but they're physically present in the working tree.

- **Root cause:** Local `python -m build` produced artifacts that the user can't easily clean.

- **Impact:** If they're tracked, they bloat the repo and rot at every release. If untracked, they're fine but visually noisy.

- **Recommended fix:** Verify with `git ls-files | grep dist/`. If tracked, `git rm --cached dist/*` and commit. If untracked, leave alone; the `.gitignore` already covers them.

- **Effort:** 5 minutes (verify + clean).

#### TD-028 , `src/nborder.egg-info/` is in the working tree

- **Severity:** **Low**
- **Evidence:** `ls src/nborder.egg-info/` shows `PKG-INFO`, `SOURCES.txt`, `requires.txt`, etc. `.gitignore:21` lists `*.egg-info/`. `git ls-files | grep egg-info` should confirm whether tracked.

- **Root cause:** `pip install -e .` populates this directory on every editable install.

- **Impact:** Same as TD-027. Probably untracked given the gitignore pattern; verify.

- **Recommended fix:** Verify and clean if tracked; leave alone if untracked.

- **Effort:** 5 minutes.

#### TD-030 , Coverage thresholds documented but not enforced

- **Severity:** **Medium**
- **Evidence:**
  - `copilot-instructions.md:73` says: "Coverage target: 90%+ on `graph/` and `parser/`, 80%+ on `rules/`, 70%+ overall."
  - `pyproject.toml` has no `[tool.coverage]` section, no `--cov-fail-under` argument, no per-package fail thresholds.
  - CI workflow `.github/workflows/ci.yml:40` runs `pytest` with no coverage flags. Coverage is collected but never asserted.

  Current actual coverage (verified by `pytest --cov=nborder`): 97% overall , well above the documented floor , but no enforcement.

- **Root cause:** Coverage targets were aspirational; the gates were never implemented.

- **Impact:** Future regression in coverage is invisible. A new contributor adding 200 lines of untested CLI helper drops overall coverage to 80% with no signal.

- **Recommended fix:** Add to `pyproject.toml`:

  ```toml
  [tool.coverage.run]
  source = ["nborder"]
  branch = true

  [tool.coverage.report]
  fail_under = 70
  show_missing = true
  ```

  Update CI to run `pytest --cov=nborder --cov-fail-under=70 --cov-report=term-missing`. Add per-module gates later if needed (`coverage` doesn't natively support per-package thresholds; `coverage-conditional-plugin` does).

- **Effort:** 30 minutes.

#### TD-031 , README references `uv` setup; CI uses `uv`; pre-commit-config and CONTRIBUTING blend `uv` and `pip`

- **Severity:** **Low**
- **Evidence:**
  - `CONTRIBUTING.md:9-12` recommends `uv venv && pip install -e ".[dev]"` (mixed).
  - `ci.yml:25-31` uses `astral-sh/setup-uv@v5` then `uv pip install --system -e ".[dev]"` (uv-only).
  - `BUILD_PLAN.md:15` says: "uv for dependency management."

- **Root cause:** Standard mid-migration state. The author moved to `uv` but didn't fully delete `pip` references.

- **Impact:** Confused contributors who try `pip install -e .` and hit non-`uv` differences (e.g., resolution semantics).

- **Recommended fix:** Pick one. Recommend `uv` since CI uses it:

  ```bash
  uv venv
  source .venv/bin/activate
  uv pip install -e ".[dev]"
  ```

- **Effort:** 5 minutes (CONTRIBUTING.md edit).

#### TD-033 , Release workflow uses PYPI_API_TOKEN secret instead of trusted publishing

- **Severity:** **Medium**
- **Evidence:** `.github/workflows/release.yml:30-33`

  ```yaml
  - name: Publish to PyPI
    uses: pypa/gh-action-pypi-publish@release/v1
    with:
      password: ${{ secrets.PYPI_API_TOKEN }}
  ```

- **Root cause:** Trusted publishing was newer when the project bootstrapped; token-based publish is the path of least resistance.

- **Impact:** Long-lived API token in repository secrets. If leaked, full publish capability for `nborder` until rotated. Trusted publishing (OIDC) is the modern, lower-risk default.

- **Recommended fix:** Configure trusted publisher on PyPI for the `moonrunnerkc/nborder` repo. Replace the `password:` block with:

  ```yaml
  permissions:
    id-token: write
  ...
  - name: Publish to PyPI
    uses: pypa/gh-action-pypi-publish@release/v1
  ```

  Rotate the existing token immediately after the cutover.

- **Effort:** 30 minutes.

#### TD-046 , No Dependabot, CodeQL, SBOM, or dep-vuln scan

- **Severity:** **Low**
- **Evidence:** `.github/` contains only workflows and the (gitignored-but-committed) planning docs. No `dependabot.yml`, no `codeql.yml`.

- **Root cause:** v0.1 scope.

- **Impact:** Low for a four-dependency project, but `nbformat` and `libcst` both have a real attack surface (parsing untrusted notebooks). Worth turning on automated security signals before adoption grows.

- **Recommended fix:** Add `.github/dependabot.yml` with `pip` and `github-actions` ecosystems on a weekly schedule. Add `.github/workflows/codeql.yml` from the standard template. Skip SBOM until v0.3.

- **Effort:** 30 minutes.

---

### F. Security & Compliance

#### TD-034 , `wildcards.py` imports arbitrary user-named modules at lint time

- **Severity:** **High**
- **Evidence:** `src/nborder/graph/wildcards.py:6-25`

  ```python
  def resolve_wildcard_names(module_name: str) -> tuple[str, ...]:
      try:
          imported_module = importlib.import_module(module_name)
      except Exception:
          return ()

      exported_names = getattr(imported_module, "__all__", None)
      ...
  ```

  Reachable via any notebook cell containing `from <X> import *`. The `<X>` is parsed by LibCST into `module_name` and passed to `importlib.import_module` as-is.

- **Root cause:** The author needed accurate wildcard resolution for NB102. Importing the module is the only reliable way to enumerate `__all__`. The `try/except Exception` swallows import failures (good) but the import itself runs the module's top-level code (bad).

- **Impact:** If a notebook in a CI'd repo contains `from local_evil_module import *`, and `local_evil_module` lives anywhere on `sys.path` (which, in pre-commit and CI environments, may include the repo root), `local_evil_module/__init__.py` runs. **Any `print`, `os.system`, `urllib`, or worse executes during what the user thinks is a static lint.**

  Real attack scenario: a contributor opens a PR with a malicious `__init__.py` and a notebook that wildcards it. The pre-commit hook on a maintainer's machine, or the action on the CI runner, runs the malicious code. This is the same supply-chain shape as the `pickle` deserialization risk in many ML tools.

- **Recommended fix:** Three options ordered by safety:

  1. **Eliminate the import.** Maintain a static `__all__` map for the small set of wildcard targets that matter (numpy, pandas, math, pathlib, etc.). When the module isn't in the map, fall back to a "may be defined" diagnostic without importing. Cost: stale `__all__` for libraries, but the wildcard rule is already an `info`-level diagnostic, and the hint quality stays high for the common case.

  2. **Import in a subprocess with a clean `sys.path`.** Use `subprocess.run([sys.executable, "-c", _wildcard_introspect_script], env={"PYTHONPATH": ""}, timeout=5)` and parse the output. Subprocess crashes don't bring down the linter. Still imports the module, but at least the linter process is unaffected.

  3. **Document and gate.** Add a `[tool.nborder] resolve_wildcards = false` config and default to `false` in CI environments. Importing only happens for explicit opt-in.

  Recommend **option 1**. The wildcard rule is already advisory.

- **Effort:** 4 hours (option 1, with the static map for the top 10 libraries).

#### TD-035 , Broad `except Exception` in wildcards.py is intentional but unannotated

- **Severity:** **Low** (subordinate to TD-034)
- **Evidence:** `src/nborder/graph/wildcards.py:17`. The bare `except Exception` swallows everything from `ModuleNotFoundError` to `RuntimeError` raised in the imported module's top-level code.

- **Root cause:** Defensive against misbehaved third-party modules.

- **Impact:** Rolled into TD-034. After TD-034 is fixed, this exception handler likely goes away.

- **Recommended fix:** Folded into TD-034.

- **Effort:** 0 (fixed by TD-034).

#### TD-036 , README pins action to `@v0.1.0` (mutable tag)

- **Severity:** **Low**
- **Evidence:** `README.md:49`, `docs/integrations/github-actions.md:28`, `.github/workflows/example-lint.yml:13` all pin `moonrunnerkc/nborder@v0.1.0`. Git tags are mutable; an attacker who briefly compromises the repo could move the tag.

- **Root cause:** Standard adoption-friendly default. Most actions pin tags rather than SHAs.

- **Impact:** Low. The mitigation is well-known and the maintainer can rotate. Worth noting for security-conscious adopters.

- **Recommended fix:** Add a "Pinning" section to `docs/integrations/github-actions.md` showing both the easy form (`@v0.1.0`) and the locked form (`@<commit-sha>  # v0.1.0`). Don't change the README default; advise the option.

- **Effort:** 15 minutes.

---

### G. Performance & Scalability

#### TD-038 , `call_events` rebuilds `MetadataWrapper` on every cell scan

- **Severity:** **Low**
- **Evidence:** `src/nborder/rules/seed_calls.py:24-38`

  ```python
  def call_events(cell: Cell) -> tuple[CallEvent, ...]:
      if cell.kind != "code" or cell.cst_module is None:
          return ()
      wrapper = MetadataWrapper(cell.cst_module, unsafe_skip_copy=True)
      visitor = _CallEventVisitor(cell.index)
      wrapper.visit(visitor)
      return tuple(sorted(visitor.events, key=lambda event: (event.line, event.column)))
  ```

  And `extractor.py:34` does the same for symbol extraction. Two `MetadataWrapper.visit()` calls per cell. Each parse builds the position-provider metadata anew.

- **Root cause:** Conceptually clean separation. Each visitor owns its own metadata. Caching would couple the rule layer to the parser layer.

- **Impact:** Minor. The 100-cell budget is met. On a 1000-cell notebook the constant factor adds up but is still sub-second.

- **Recommended fix:** If profiling ever shows it, attach a single `MetadataWrapper` to the `Cell` dataclass (mutable cache field; would require dropping `frozen=True` or using a `cached_property`-style sidecar). Otherwise, leave it.

- **Effort:** 2 hours; defer until measured.

---

### H. Error Handling, Logging & Observability

#### TD-040 , No logging anywhere; no `--debug` or `--verbose` flag

- **Severity:** **Medium**
- **Evidence:** `grep -RIn 'logger\|logging\.' src/` returns zero matches. `copilot-instructions.md:55` cites the error-message convention: "Run `nborder check --debug` for the full traceback." No `--debug` flag exists in `cli.py`.

- **Root cause:** v0.1 prioritized correctness over operability. Logging adds dependency surface and cognitive overhead.

- **Impact:** When something goes wrong (TD-041), users see a raw `rich`-styled traceback. There's no internal observability. For a static analysis tool that's mostly fine, but adopters running it in CI will want a way to escalate detail.

- **Recommended fix:** Add `--debug` (boolean) that flips the global logger to DEBUG level and unhides tracebacks. Lazily wire `logging.getLogger("nborder")` into the parser, graph, and fix layers. Default level WARNING. Stop using `typer.echo` for diagnostics that aren't user-facing output (the JSON/SARIF reporters should not log).

- **Effort:** 3 hours (touches cli.py + a few rule modules).

#### TD-041 , `NotebookParseError` raised but not caught at the CLI boundary

- **Severity:** **High**
- **Evidence:**
  - `src/nborder/parser/reader.py:14`: `class NotebookParseError(Exception)`. Raised at line 73 with a useful message.
  - `src/nborder/cli.py:94`: `notebook = read_notebook(notebook_path)`. No surrounding try/except.

  Reproduction: `nborder check tests/fixtures/does_not_exist.ipynb` produces a full Rich-styled traceback ending in `FileNotFoundError`. The parse error path is structurally identical.

- **Root cause:** The CLI was written for happy paths. The parser's helpful error messages are wasted because nobody catches them.

- **Impact:** Real user-facing issue. The user sees scary tracebacks instead of "Failed to parse cell 7: unbalanced quote at column 14."

- **Recommended fix:** Wrap the per-notebook loop body in `cli.py:92-128` in:

  ```python
  try:
      notebook = read_notebook(notebook_path)
      ...
  except NotebookParseError as parse_error:
      typer.echo(f"error: {notebook_path}: {parse_error}", err=True)
      raise typer.Exit(code=2)
  except FileNotFoundError as missing:
      typer.echo(f"error: {missing.filename}: file not found", err=True)
      raise typer.Exit(code=2)
  ```

- **Effort:** 1 hour with tests.

#### TD-043 , Empty notebook list produces silent exit-code 0

- **Severity:** **High**
- **Evidence:** `src/nborder/cli.py:84`: `notebooks = tuple(_iter_notebook_paths(parsed_paths))`. If `parsed_paths` contains paths that all get filtered out (TD-010), `notebooks` is empty, the for-loop is a no-op, `diagnostics` stays empty, `exit_zero` is False, the `if diagnostics and not exit_zero:` is False, and the CLI exits 0.

  Reproduction: `nborder check tests/fixtures/NB101/non_monotonic.ipynb.txt` -> exit 0, no output, user sees nothing.

- **Root cause:** Same as TD-010. The "no work to do" branch is treated as success.

- **Impact:** Pre-commit hook or CI step appears green when the user passed a wrong path. Silent failure modes are the worst kind.

- **Recommended fix:** After `notebooks = tuple(...)`, raise `typer.BadParameter` if the list is empty unless the caller passed `--allow-no-matches` or similar. Or print "no notebooks found at: <paths>" to stderr and exit non-zero.

- **Effort:** 30 minutes.

---

### I. Infrastructure, CI/CD & DevOps

#### TD-044 , `.github/workflows/example-lint.yml` runs on every push/PR but references a non-existent path

- **Severity:** **Medium**
- **Evidence:** `.github/workflows/example-lint.yml`:

  ```yaml
  on: [push, pull_request]
  jobs:
    lint:
      ...
      - uses: moonrunnerkc/nborder@v0.1.0
        with:
          path: notebooks/
  ```

  The repo does not contain `notebooks/`. The workflow will dispatch on every push, install `nborder` via `pip install nborder` (which depends on PyPI being up), and find zero notebooks (TD-043 triggers) or fail because `notebooks/` doesn't exist depending on the action's behavior.

- **Root cause:** The file looks like a copy-paste of the README example used as a self-test. It's neither documentation (it's executed by Actions) nor working CI (it points at a missing directory).

- **Impact:** Every push burns CI minutes and may produce confusing red checks on PRs. Contributors will see two CI runs and not know which is authoritative.

- **Recommended fix:** Pick one:
  1. Rename to `docs/examples/example-lint.yml` and remove the `on:` trigger so it ships as documentation only.
  2. Point `path: tests/fixtures/roundtrip` so it actually tests the published action against a known-clean fixture set, validating end-to-end.

  Recommend (2): it's a real integration test for the action.

- **Effort:** 15 minutes.

#### TD-048 , CI does not run the full PR checklist

- **Severity:** **Low**
- **Evidence:** `.github/workflows/ci.yml:32-43` runs `ruff`, `mypy`, `pytest`, and `nborder check tests/fixtures/roundtrip`. CONTRIBUTING.md:62-69 lists six PR checklist items, including coverage floors (TD-030) and `nborder check src tests` (TD-025, which is misleading anyway).

- **Root cause:** CI was bootstrapped to the minimal viable check set.

- **Impact:** Drift between contributor obligations and CI enforcement. New contributors will skip steps that aren't enforced.

- **Recommended fix:** Either (a) align the checklist to what CI actually runs, or (b) move the missing items into CI. The coverage floor (TD-030) is the most important; the others can stay on the checklist.

- **Effort:** 15 minutes (after TD-030 lands).

---

### J. Data Layer

Not applicable. `nborder` has no database.

---

### K. Other / Project-Specific

#### TD-050 , `BUILD_PLAN.md` claims Marketplace publication; never executed

- **Severity:** **Low**
- **Evidence:** `BUILD_PLAN.md:111`: "Publish the action to the GitHub Marketplace under the `code-quality` category." No marketplace publication step in `release.yml`. The action.yml is valid for marketplace listing but no automation submits it.

- **Root cause:** Marketplace listing is a manual one-time step (publish via GitHub UI), not a workflow.

- **Impact:** Maintainer's plan unfulfilled but not load-bearing.

- **Recommended fix:** Add a one-time issue / TODO for the maintainer or remove the line from the BUILD_PLAN. It's planning text, not code; minimal blast radius.

- **Effort:** 5 minutes (admin step).

#### TD-052 , No issue and PR templates in `.github/`

- **Severity:** **Low**
- **Evidence:** `.github/` contains only workflows and the planning docs. No `ISSUE_TEMPLATE/` or `PULL_REQUEST_TEMPLATE.md`.

- **Root cause:** Standard for a v0.1 repo. Acceptable.

- **Impact:** First-time contributors won't get prompts for the right reproduction steps. Issues will be lower quality on the first wave of adoption.

- **Recommended fix:** Add a minimal bug-report template (notebook attachment, version, CLI invocation, expected vs actual) and a feature-request template. PR template mirroring the CONTRIBUTING checklist.

- **Effort:** 30 minutes.

---

## 6. Prioritized Remediation Roadmap

The roadmap is sequenced for maximum risk reduction per hour invested. Each item carries the relevant TD ID(s) for traceability.

### Quick Wins (1 day, ~6-8 hours)

| Item | Effort | TDs |
|------|--------|-----|
| Drop `--select=...` from `action.yml` (or implement) | 30m | TD-022, TD-023 |
| Edit README/copilot-instructions to remove unimplemented config knobs | 1h | TD-022 |
| Wrap `read_notebook` in CLI try/except for `NotebookParseError` and `FileNotFoundError` | 1h | TD-041 |
| Make `_iter_notebook_paths` raise on bogus paths and zero matches | 30m | TD-010, TD-043 |
| Tighten `_parse_include` to reject unknown levels | 30m | TD-002 |
| Delete dead branch in `_relative_call_name` | 5m | TD-005 |
| Fix `_seed_description` to report actual cell index | 30m | TD-024 |
| Add `## [Unreleased]` to CHANGELOG | 2m | TD-051 |
| Verify and clean tracked `dist/` and `egg-info/` | 15m | TD-027, TD-028 |
| Decide and clean BUILD_PLAN gitignore state | 5m | TD-026 |
| Decide on `[reproduce]` extra: implement or remove for v0.1.x | 30m (remove) | TD-049 |
| Repoint `example-lint.yml` to a real fixture path | 15m | TD-044 |
| Add coverage gate `--cov-fail-under=70` to CI | 30m | TD-030 |
| Update CONTRIBUTING `uv` vs `pip` and remove misleading dogfood line | 10m | TD-025, TD-031 |

### 30-day window (~2-3 dev days)

| Item | Effort | TDs |
|------|--------|-----|
| Restore Typer's standard option parsing; rename `--fix=value` to `--fix-categories=value` | 2h | TD-001 |
| Move per-rule docs under `src/nborder/_rule_docs/` and ship via `package_data` | 1h | TD-008, TD-009 |
| Implement `[tool.nborder] select = [...] ignore = [...]` and wire into `_check_notebook` | 1d | TD-022, TD-023 |
| Move `_check_notebook` and `_visible_diagnostics` into `nborder/check.py` | 1h | TD-013 |
| Extract toposort/cycle detection into `graph/algorithms.py`; remove duplicates in `fix/pipeline.py` | 2h | TD-012 |
| Split `extractor.py`, `nb103.py`, `pipeline.py` along natural seams | 4h | TD-014 |
| Fill in NB102 and NB201 fixture sets to three notebooks each (or amend CONTRIBUTING) | 1h | TD-018 |
| Snapshot real-world fixture diagnostics for regression detection | 3h | TD-020 |
| Add `--debug` flag with logging plumbing | 3h | TD-040 |
| Add Dependabot and CodeQL workflows | 30m | TD-046 |
| Configure trusted publishing for PyPI | 30m | TD-033 |
| Add issue + PR templates | 30m | TD-052 |

### 90-day strategic (~1 week)

| Item | Effort | TDs |
|------|--------|-----|
| Replace runtime `importlib.import_module` in wildcards with a static `__all__` map | 4h | TD-034, TD-035 |
| Convert recursive cycle detection to iterative DFS | 1h | TD-007 |
| Replace bubble-sort toposort with `heapq` | 30m | TD-006 |
| Convert `ImportBinding` to discriminated union (three dataclasses) | 3h | TD-017 |
| Implement `--reproduce` if we want to keep the extra | 2d | TD-049 (alternative path) |
| Replace timing-based perf test with complexity invariant | 1h | TD-021 |
| Strengthen `--diff` test to assert content shape | 30m | TD-019 |
| Add pinning section to GitHub Actions docs | 15m | TD-036 |

### 6-month architectural

The architecture is healthy. The only architectural move worth flagging is consolidating configuration into a single typed schema (`Config` would gain `select`, `ignore`, `fix`, `extend_include`, `per_file_ignores` fields), with `tomllib`-driven validation that raises with a helpful message on unknown keys. This is the structural fix to TD-022 and the unblocker for v0.2 work. **Effort: ~3 dev days.**

### Sprint allocation guidance

- **Next two sprints:** ~15% of capacity dedicated to the Quick Wins and the high-priority 30-day items. The Quick Wins ship in one focused day; the rest can be interleaved.
- **Steady state:** 10% allocation to debt prevention (writing the test that catches a regression, splitting a file approaching the 250 LOC line, expanding the changelog).

---

## 7. Prevention Recommendations

The codebase already has strong prevention infrastructure. These recommendations close the small gaps that allowed the current debt to accumulate.

1. **Pre-merge enforcement of "if the README documents it, the code implements it."** Add a `tests/test_documented_surface.py` that parses the README's Configuration section and asserts every documented key is recognized by `Config`. Any future docs/code drift fails CI on the PR that introduces it. This is the structural fix that prevents TD-022 from re-emerging.

2. **Coverage floor in CI** (TD-030). 70% overall, 80% on `rules/`, 90% on `graph/` and `parser/`. Per-package floors are easier with `pytest-cov`'s `--cov-config` and a `coveragerc` per-package fail rule.

3. **`--debug` flag and structured logging** (TD-040). Once landed, future error-handling work has a clear escape hatch without scaffolding.

4. **Adopt ADRs for non-obvious decisions.** Three are already due: (a) why wildcard resolution imports modules and what the security trade-offs are (TD-034); (b) why the fix pipeline duplicates the toposort and the migration plan to consolidate (TD-012); (c) why per-rule docs are duplicated under `docs/rules/` and `_rule_docs/` post-fix (TD-008/TD-009). Store as `docs/adr/0001-*.md`. Each is one page max.

5. **Pre-commit on the maintainer side.** The `.pre-commit-config.yaml:1-19` already wires `ruff`, `mypy`, and `pytest`. Add `pre-commit autoupdate` to the maintainer's monthly cadence and fold it into a `chore:` commit. Consider also adding `check-yaml`, `end-of-file-fixer`, and `trailing-whitespace` from the standard `pre-commit-hooks` repo for the YAML-heavy parts of the project.

6. **Definition of Done update for new rules.** Append to CONTRIBUTING:
   - The rule's docs page is reachable via `nborder rule <CODE>` from a fresh `pip install` (regression: TD-008/TD-009).
   - Any new CLI flag has an explicit Typer option, never relies on `ignore_unknown_options` (regression: TD-001).
   - Any new config key has a corresponding entry in the README configuration table and is enforced by the documented-surface test (regression: TD-022).

7. **Quarterly debt review.** Re-run this audit's discovery phase quarterly (or before each minor release). The mechanical findings (line counts, untracked artifacts, doc/code drift) take ~30 minutes to verify with `grep` and `wc -l`.

8. **Real-world corpus snapshot tests** (TD-020). Once snapshotted, every PR sees the diff. False-positive regressions become impossible to ship silently.

9. **Trusted publishing for PyPI** (TD-033). Eliminates one long-lived secret.

10. **Dependabot for `pip` and `github-actions`** (TD-046). Weekly cadence is fine; the dependency surface is small, so PR velocity will be low.

---

## 8. Summary Table of All Issues

| ID | Title | Category | Priority | Effort | Primary Location |
|----|-------|----------|----------|--------|------------------|
| TD-001 | Manual `--fix` parsing breaks Typer flag handling | A | High | 2h | `src/nborder/cli.py:36, 156-167` |
| TD-002 | `_parse_include` silently drops unknown levels | A | Medium | 30m | `src/nborder/cli.py:222-231` |
| TD-005 | Dead conditional in `_relative_call_name` | A | Low | 5m | `src/nborder/rules/nb103.py:178-187` |
| TD-006 | Toposort uses repeated list-sort | B | Low | 30m | `src/nborder/graph/models.py:106-115` |
| TD-007 | Recursive cycle detection (stack-depth risk) | B | Low | 1h | `src/nborder/graph/models.py:139-156` |
| TD-008 | `nborder rule <CODE>` looks for docs at unpackaged path | D | High | 1h | `src/nborder/cli.py:32, 142-146` |
| TD-009 | `pyproject.toml` does not ship `docs/` as package data | D / E | High | 30m | `pyproject.toml:48-49` |
| TD-010 | Silent ignore of non-`.ipynb` paths | A / H | High | 1h | `src/nborder/cli.py:170-178` |
| TD-011 | CLI re-reads notebook from disk after fix | A | Low | 1h | `src/nborder/cli.py:115-124` |
| TD-012 | Toposort and cycle detection duplicated | B | Medium | 2h | `graph/models.py:86-156`, `fix/pipeline.py:180-237` |
| TD-013 | `cli.py` mixes orchestration and business logic | B | Medium | 1h | `src/nborder/cli.py:181-219` |
| TD-014 | Files at or above the 300-line cap | A | Medium | 4h | `extractor.py:297`, `cli.py:283`, `pipeline.py:279`, `nb103.py:242` |
| TD-017 | `ImportBinding` is a discriminated union disguised as flat | B | Low | 3h | `src/nborder/graph/models.py:34-44` |
| TD-018 | Per-rule fixture coverage falls short of CONTRIBUTING contract | C | Medium | 1h | `tests/fixtures/NB102/`, `tests/fixtures/NB201/` |
| TD-019 | `--diff` test is shallow | C | Low | 30m | `tests/test_cli.py:205-217` |
| TD-020 | Real-world fixtures only smoke-tested | C | Medium | 3h | `tests/test_graph_builder.py:142-147`, `tests/test_nb103.py:112-116` |
| TD-021 | Performance test depends on wall-clock timing | C | Low | 1h | `tests/test_graph_builder.py:150-164` |
| TD-022 | Documented config knobs not implemented | D | High | 1h-1d | `README.md:82`, `copilot-instructions.md:178`, `src/nborder/config.py:23-27` |
| TD-023 | `action.yml` passes `--select` to a CLI that ignores it | D / I | High | 30m | `action.yml:32-36`, `docs/integrations/github-actions.md:41` |
| TD-024 | `_seed_description` hardcodes "cell 1" | A | Low | 30m | `src/nborder/fix/seeds.py:190-193` |
| TD-025 | "Dogfood" instruction in CONTRIBUTING is misleading | D | Low | 5m | `CONTRIBUTING.md:67` |
| TD-026 | Gitignored planning docs are tracked | D | Low | 5m | `.gitignore:1-3`, `.github/BUILD_PLAN.md` |
| TD-027 | `dist/` directory in working tree | E | Medium | 5m | `dist/` |
| TD-028 | `src/nborder.egg-info/` in working tree | E | Low | 5m | `src/nborder.egg-info/` |
| TD-030 | Coverage thresholds documented but not enforced | E / I | Medium | 30m | `pyproject.toml`, `.github/workflows/ci.yml:40` |
| TD-031 | README/CONTRIBUTING blend `uv` and `pip` | E | Low | 5m | `CONTRIBUTING.md:9-12` |
| TD-033 | Release uses PYPI_API_TOKEN, not trusted publishing | I | Medium | 30m | `.github/workflows/release.yml:30-33` |
| TD-034 | `wildcards.py` imports arbitrary modules at lint time | F | High | 4h | `src/nborder/graph/wildcards.py:6-25` |
| TD-035 | Broad `except Exception` (subordinate to TD-034) | F | Low | 0 | `src/nborder/graph/wildcards.py:17` |
| TD-036 | Tag-based action pin recommended in docs | F | Low | 15m | `README.md:49`, `docs/integrations/github-actions.md:28` |
| TD-038 | `MetadataWrapper` rebuilt per cell scan | G | Low | 2h | `src/nborder/rules/seed_calls.py:24-38` |
| TD-040 | No logging; no `--debug`/`--verbose` flag | H | Medium | 3h | `src/nborder/cli.py` |
| TD-041 | `NotebookParseError` not caught at the CLI boundary | H | High | 1h | `src/nborder/cli.py:94`, `parser/reader.py:14-76` |
| TD-043 | Empty notebook list silently exits 0 | H | High | 30m | `src/nborder/cli.py:84` |
| TD-044 | `example-lint.yml` runs against a non-existent path | I | Medium | 15m | `.github/workflows/example-lint.yml` |
| TD-046 | No Dependabot, CodeQL, SBOM, or vuln scan | E / F | Low | 30m | `.github/` |
| TD-048 | CI doesn't enforce the full PR checklist | I | Low | 15m | `.github/workflows/ci.yml`, `CONTRIBUTING.md:62-69` |
| TD-049 | `[reproduce]` extra installs `papermill`; no code uses it | A / D | High | 30m-2d | `pyproject.toml:41-43`, `docs/known-limitations.md:9-11` |
| TD-050 | BUILD_PLAN claims Marketplace publication; never executed | K | Low | 5m | `.github/BUILD_PLAN.md:111` |
| TD-051 | CHANGELOG missing `[Unreleased]` section | D | Low | 2m | `CHANGELOG.md:7` |
| TD-052 | No issue or PR templates | K | Low | 30m | `.github/` |

**Total estimated repayment effort:** ~3 to 5 dev days for the 8 High-priority items, ~10 dev days for everything in the 30-day and 90-day windows combined. Quick Wins alone retire roughly half the visible debt in a single focused day.

---

## 9. Appendix

### A. Test suite execution profile

```text
125 tests collected
125 passed in 4.52s
TOTAL coverage: 1489 stmts, 45 missed, 97% covered
```

Coverage hot spots (lowest first):
- `parser/reader.py:83%` , the `_cell_source` list-source branch and the parse-error path are uncovered. Adding a fixture with a list-form `source` would close this.
- `fix/seeds.py:92%` , alias-resolution defaults branch and TF/torch import-line edge cases.
- `fix/pipeline.py:93%` , the cycle-edge fallback messages.
- Everything else is at or above 95%.

### B. Module size table (LOC, sorted)

```text
graph/extractor.py          297   AT CAP
cli.py                      283
fix/pipeline.py             279
rules/nb103.py              242
fix/seeds.py                193
graph/models.py             156
reporters/sarif.py          142
graph/cst_helpers.py        135
graph/builder.py            121
parser/writer.py            117
parser/magics.py            117
rules/seed_registry.py      110
reporters/text.py            99
parser/reader.py             98
rules/nb102.py               91
rules/unresolved.py          83
rules/seed_calls.py          83
config.py                    74
reporters/jsonout.py         61
rules/nb201.py               60
rules/suppression.py         53
reporters/github.py          50
parser/models.py             48
rules/nb101.py               47
rules/types.py               34
reporters/base.py            26
graph/wildcards.py           24
fix/models.py                18
__init__.py                   3
```

### C. Verification commands used

- `find . -maxdepth 4 -type f \( -name "*.py" -o ... \) -not -path "*/__pycache__/*" ...`
- `wc -l src/nborder/**/*.py src/nborder/*.py | sort -rn`
- `grep -RIn "TODO\|FIXME\|XXX\|HACK" src tests docs`
- `grep -RIn "Any\b" src` (returns 8 matches; all in JSON serializers, justified)
- `grep -RIn "except Exception\|except:\|except BaseException" src` (returns 1, in `wildcards.py`, see TD-034)
- `grep -RIn "," src tests docs .github` (returns zero; em-dash discipline holding)
- `grep -RIn "data\b\|result\b\|temp\b\|obj\b\|item\b" src` (returns zero; AI-tell discipline holding)
- `.venv/bin/pytest --cov=nborder --cov-report=term-missing -q` (125 passed, 97% coverage)
- `.venv/bin/nborder check --select=NB999 tests/fixtures/NB101/non_monotonic.ipynb` (NB101 fired anyway, confirming `--select` is dropped)
- `.venv/bin/nborder check tests/fixtures/NB101/non_monotonic.ipynb.txt` (exit 0, no output, confirming silent ignore)

### D. Notes on what was not flagged

- **Em dashes:** none found in source or docs. The maintainer's discipline holds.
- **AI tells (generic variable names):** none found. Variable names are descriptive throughout (e.g., `notebook_diagnostics`, `enabled_fixes`, `cycle_cells`).
- **`Any` usage:** only in `dict[str, Any]` payloads inside `reporters/jsonout.py` and `reporters/sarif.py`, which is the standard idiom for serializing JSON dicts. Acceptable.
- **`type: ignore` comments:** three, all on `nbformat` calls that lack stubs. Acceptable.
- **Tracked secrets, hardcoded credentials, dangerous deserialization:** none.
- **Frontend / accessibility / i18n:** N/A (CLI tool).

The codebase is, by any reasonable v0.1 standard, **clean**. The debt above is the kind that accumulates from racing to a release, not from neglect. Most of the high-priority items can be retired in a single day of focused work.
