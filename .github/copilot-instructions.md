# nborder : Copilot Instructions

You are working on **nborder**, a Jupyter notebook linter and auto-fixer for hidden-state and execution-order bugs. The tool runs as a CLI, in pre-commit, and as a GitHub Action. Treat ruff as the UX reference and nbqa as the integration reference. The differentiator is cross-cell dataflow analysis; everything else (style, imports) is already covered elsewhere and is explicitly out of scope for v0.1.

Static-first is the default. A fresh-kernel rerun is planned for a future release and must stay opt-in.

---

## Non-negotiable invariants

These rules cannot be bent. Violation breaks adopters silently and is a release blocker.

**Byte-stable round-trip.** `nborder check --fix file.ipynb` on a notebook with no findings must produce a file whose JSON bytes are identical to the input. Test this on v4.0, v4.4, and v4.5 notebooks via golden fixtures asserted with `filecmp.cmp(original, rewritten, shallow=False)`. If `nbformat.write` mutates trailing newlines, line endings, or `nbformat_minor`, fix the writer wrapper, not the test.

**Never touch what wasn't requested.** Outputs, `execution_count`, cell metadata, and notebook-level metadata are read-only by default. The only fix that may modify `execution_count` is `--fix=reorder`, and that fix clears all execution counts to `null` rather than reassigning them.

**Magic and shell semantics are real bindings.** `files = !ls *.csv` defines `files`. `%%capture out` defines `out`. `%load_ext autoreload` mutates import semantics. The parser must strip these into typed metadata before LibCST sees the cell, and the dataflow graph must record the bindings they create. Treating magics as parse errors or skipping them silently produces false-positive NameErrors on every real-world notebook.

**Respect papermill conventions.** Cells tagged `parameters` or `injected-parameters` define names at logical position zero in the dataflow graph regardless of their source-order position. Cells tagged `nborder:skip` are excluded from analysis. Without these, NB201 and NB102 will false-positive on parameterized notebooks, which is half the production data-science workflow.

**Library-aware seed injection.** Do not inject `np.random.seed(42)` blindly. Detect which RNG library is actually imported and inject the modern API for that library. The mapping table is below; treat it as authoritative.

---

## Architecture

Five layers, each with a clear boundary. Do not skip layers. Do not let rule code call into the parser or fix code call into rule code; the only legal upward dependency is rules → graph → parser, and fix consumes diagnostics produced by rules.

```
nborder/
├── parser/      ipynb -> internal Cell model; magic stripping; tag extraction
├── graph/       cross-cell dataflow; symbol defs/uses; topo sort; cycle detection
├── rules/       NB1xx ordering, NB2xx dataflow, NB3xx imports (v0.2), etc.
├── fix/         CST transformations; reorder, seed inject, hoist (v0.2), extract (v0.2)
├── dynamic/     future fresh-kernel rerun; opt-in only
└── reporters/   text, json, github-actions, sarif
```

The parser produces a `Notebook` object containing typed `Cell` objects. The graph layer consumes `Notebook` and produces a `DataflowGraph` with explicit `SymbolDef`, `SymbolUse`, and `Import` nodes plus a per-cell adjacency list. Rules consume the graph and produce `Diagnostic` objects with stable codes, messages, span info (cell index + line/column within the cell), severity, and an optional `FixDescriptor`. Reporters consume diagnostics. The fix engine consumes `FixDescriptor` lists and produces a rewritten `Notebook` that the writer serializes back to disk.

---

## Coding conventions

**Python 3.10+.** Use `match` statements where they're clearer than `if/elif` chains. Use `from __future__ import annotations` everywhere for cleaner type hints.

**Type hints throughout.** No bare `Any`. If you need an escape hatch, use `object` and narrow with `isinstance`, or define a `Protocol`. Public functions get full annotations including return types. Private helpers can be looser if the call site is local.

**Snake_case files and modules** per PEP 8. One concept per module. If a module crosses ~250 lines, split it; the cap is 300 and that's a hard ceiling, not a target.

**Docstrings on every public function and class.** Google style. Include at least a one-line summary; add Args/Returns/Raises when the signature isn't self-explanatory.

**Named imports.** No `from foo import *`. No re-exports unless the package boundary requires it.

**Errors include both what failed and what to do.** "Failed to parse cell 7: unbalanced quote at column 14. Run `nborder check --debug` for the full traceback" beats "ParseError" every time.

**Dataclasses for value objects.** Use `@dataclass(frozen=True, slots=True)` for `Cell`, `SymbolDef`, `SymbolUse`, `Diagnostic`, `FixDescriptor`. Mutability is the exception, not the default.

---

## Testing requirements

**Tests validate behavior, not wiring.** A test named `test_dataflow_graph_detects_use_before_assign_across_cells` describes what's being verified. A test named `test_build_graph_calls_visit_cell` describes the implementation and is worthless. Rename or delete the latter.

**Per-rule fixture notebooks.** Each rule has at least three `.ipynb` fixtures: one that triggers the rule, one that almost triggers it but doesn't (the boundary case), and one with the fix applied that should round-trip clean. Fixtures live under `tests/fixtures/<rule_code>/`.

**Golden round-trip suite.** A directory of clean notebooks (different versions, different content shapes: pure code, mixed markdown, magics, shell commands, papermill-tagged) that all assert byte-identical output after `check --fix`. Run this on every commit. If it fails, the CI is red until it's fixed.

**Graph module gets direct unit tests, not just integration tests through rules.** The dataflow graph is the project's intellectual property. Test `add_cell`, `resolve_symbol`, `topological_sort`, and `detect_cycle` directly with synthetic inputs.

**No mocks where the real thing is testable.** Don't mock `nbformat.read`; use a real fixture file. Don't mock LibCST; parse a real string. Mocks are reserved for filesystem and network boundaries.

**Coverage target: 90%+ on `graph/` and `parser/`, 80%+ on `rules/`, 70%+ overall.** Coverage is a floor, not a goal. A green coverage badge with shallow tests is worse than 70% with deep tests.

---

## Rule taxonomy (v0.1 scope)

Four rules ship in v0.1. Each has a stable code, a short message, a docs page with bad/good notebook examples, and an associated fix where applicable.

| Code | Name | Detection | Fix |
|------|------|-----------|-----|
| NB101 | Non-monotonic execution counts | Pure metadata pass on `cell.execution_count` | `--fix=reorder` clears all counts; aggressive variant reorders cells to match recorded execution order |
| NB102 | Won't survive Restart-and-Run-All | Walk cells in source order against the dataflow graph; flag any use of an undefined name | No auto-fix; the user must restructure |
| NB201 | Use-before-assign across cells | Symbol used in cell N where its only definition is in cell M with M > N (source order) | `--fix=reorder` topologically sorts cells when the dependency graph is a DAG |
| NB103 | Stochastic library used without seed | Detect imports of known RNG libraries and check for a seed call before first use | `--fix=seeds` injects a library-appropriate seed cell |

Rule codes are stable forever. Renaming or recoding is a breaking change. Reserved blocks: NB1xx ordering/reproducibility, NB2xx dataflow, NB3xx imports (v0.2), NB4xx hygiene (v0.2), NB5xx extraction (v0.3+).

---

## Library-aware seed injection (NB103 fix)

This is the table the seed injector consults. Adding a library means adding a row here, a fixture, and a test; do not hard-code library detection inside the fix logic.

| Imported as | Inject |
|-------------|--------|
| `numpy` / `numpy.random` | `rng = np.random.default_rng(42)` (modern API, not `np.random.seed`) |
| `random` (stdlib) | `random.seed(42)` |
| `torch` | `torch.manual_seed(42)` plus `torch.cuda.manual_seed_all(42)` if `torch.cuda` is also used |
| `tensorflow` | `tf.random.set_seed(42)` |
| `jax` | Note in diagnostic that JAX requires explicit `PRNGKey` plumbing; do not auto-inject because the fix would need to thread a key through every random call |
| `sklearn` | Diagnostic only; sklearn estimators take `random_state` as a constructor kwarg, no global seed exists |

The seed value is configurable via `[tool.nborder.seeds] value = 42`. Default to 42.

---

## Magic stripping (parser pass)

Strip the following before LibCST parses a cell, recording each into `Cell.magics`:

- Line magics: `%name args`
- Cell magics: `%%name args` (the entire cell body becomes the magic argument; some magics, like `%%capture out`, still produce bindings)
- Shell escapes: `!command` and `name = !command` (the assignment form creates a binding)
- Help syntax: `name?` and `name??` (no binding, no analysis impact)
- Auto-call: lines starting with `,`, `;`, `/` (rare, but valid IPython)

Maintain a small registry of known magics that produce bindings or import-side-effects. `%%capture out` defines `out`. `%load_ext autoreload` plus `%autoreload 2` changes import semantics; record this in `Notebook.metadata` and use it to relax NB103's "first use" detection because autoreload re-runs imports.

---

## What's out of scope for v0.1

Do not build these in v0.1, even if they're easy:

- Style rules (line length, quote style, formatting). Ruff and Black already handle this via nbqa. Building parallel rules dilutes the unique value proposition.
- Import sorting and hoisting. Ruff's `I` rules handle this. Reserved as NB3xx for v0.2 and only if there's clear demand.
- Output stripping. `nb-clean` and `nbstripout` already do this well. Do not compete on commodity features.
- Cell extraction to sibling `.py` modules. Reserved as NB5xx for v0.3+. The UX design for "which cell becomes which file" is the hard part and shouldn't be rushed.
- Multi-language kernels. Python only in v0.1. The IPython kernel covers ~95% of notebooks in the wild; supporting R or Julia adds parser surface for marginal user gain.

---

## Forbidden patterns

These show up in AI-generated code and are immediate review blockers.

- Generic variable names: `data`, `result`, `temp`, `obj`, `item`. Use names that describe the value.
- Comments that restate what the code does. `# Loop over cells` above `for cell in cells:` is noise. Comments explain *why*, not *what*.
- Symmetrical try/except blocks that catch and re-raise the same exception with no added context.
- Defensive type checks at the top of functions that already have type hints.
- Any use of `any` as a variable name (collides with the builtin).
- Em dashes anywhere: code, comments, docstrings, error messages, tests, fixtures. Use commas, colons, semicolons, parentheses, or sentence breaks.

---

## Dependencies

Keep the install footprint tight. `pip install nborder` should complete in under 2 seconds on a warm cache.

Required:
- `nbformat` for ipynb I/O
- `libcst` for code rewrites that preserve formatting
- `typer` for CLI
- `rich` for diagnostic output

Do not add `numpy`, `pandas`, `scikit-learn`, or any heavy data-science library as a runtime dependency. The tool inspects code that uses them; it does not run that code.

---

## CLI surface (target shape)

The CLI mirrors ruff's mental model so adopters don't have to learn anything new.

- `nborder check path/` runs all enabled rules
- `nborder check --fix path/` applies safe fixes and writes back
- `nborder check --fix=reorder,seeds path/` opts into specific fix categories
- `nborder check --diff path/` shows changes without writing
- `nborder check --output-format=json path/` for CI consumption
- `nborder rule NB101` prints the rule's documentation
- `nborder config` lists effective configuration

Configuration currently lives under `[tool.nborder.seeds]` in `pyproject.toml`. Project-wide rule selection is reserved for v0.2.

---

## Pull request checklist

Before opening a PR, verify locally:

1. `nborder check src/ tests/` passes (yes, dogfood)
2. `pytest` passes with no skipped tests except those gated on optional extras
3. `pytest --cov=nborder` shows no module dropping below its coverage floor
4. The golden round-trip suite passes on all three notebook versions
5. New rules ship with at least three fixture notebooks and a docs page under `docs/rules/`
6. `CHANGELOG.md` has an entry under `## [Unreleased]` describing the change in adopter-facing terms

If the PR adds a fix, the description must include a before/after diff of a real fixture notebook so reviewers can sanity-check the transformation visually.
