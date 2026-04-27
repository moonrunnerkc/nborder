# nborder : Build Plan

Target: ship `nborder` v0.1.0 to PyPI in 4 to 6 weeks of focused part-time work, with a working demo at the end of week 1 and the four MVP rules functional by end of week 3. The plan is sequenced so that each phase produces a usable artifact and the project never enters a "almost working" state for more than a few days at a time.

The phasing follows the dependency graph of the code, not an arbitrary calendar. Each phase has explicit entry and exit gates. Don't move to the next phase until the current gate is green.

---

## Phase 0 : Claim names and scaffold (day 1)

**Goal:** lock the brand and produce a repository skeleton that can already run a no-op CLI.

Reserve `nborder` on PyPI by uploading a 0.0.1 placeholder (a working `pyproject.toml` with no source, just a stub package). PyPI squatting prevention is the only point here; the placeholder doesn't need to do anything. Create `github.com/moonrunnerkc/nborder` and push the initial commit. Add the standard files: `LICENSE` (MIT), `README.md` (placeholder pointing to "v0.1 in progress"), `pyproject.toml` with the dependency list from the copilot-instructions, `.github/copilot-instructions.md` (the file we just wrote), `.github/workflows/ci.yml` skeleton, `.pre-commit-hooks.yaml` skeleton, `tests/` directory with a single `test_smoke.py` that imports the package, and a `src/nborder/__init__.py` exposing `__version__`.

Set up the dev environment: `uv` for dependency management (faster than pip-tools, increasingly standard), `pytest` + `pytest-cov` for testing, `ruff` for the project's own linting (yes, dogfood adjacent tools), `mypy --strict` for type checking on `src/`, `pre-commit` configured to run ruff, mypy, and pytest on commit.

**Exit gate:** `pip install -e .` succeeds, `pytest` passes the smoke test, `mypy --strict src/` returns clean, `ruff check src/ tests/` returns clean, the placeholder is live on PyPI, the repo is public on GitHub.

---

## Phase 1 : Parser and cell model (days 2 to 4)

**Goal:** produce a typed `Notebook` object from any `.ipynb` file, with magic-stripping done correctly and tags preserved.

Build the parser in this order: read the ipynb via `nbformat.read(path, as_version=4)`, walk cells, classify each as code/markdown/raw, for code cells run the magic-stripping pre-pass, parse the stripped source with LibCST, attach the original source, magic list, tag set, and execution count to a `Cell` dataclass. Build the writer that round-trips a `Notebook` back to disk. The writer is the dangerous part because `nbformat.write` has subtle defaults; wrap it and test the byte-stable invariant from day one.

Key implementation decisions to lock in here: cell IDs are preserved unchanged from the source notebook, even if they're missing or malformed (regenerating them breaks git diffs); markdown cells are stored but never modified; raw cells are passed through opaque; the `nbformat_minor` field on the notebook is preserved exactly, never upgraded silently.

The magic-stripping registry starts small: line magics (`%`), cell magics (`%%`), shell escapes (`!`), shell-assignment (`name = !cmd`), and help syntax (`?`, `??`). Each has a unit test.

Ship NB101 (non-monotonic execution counts) the same day the parser lands. NB101 is a pure metadata check, requires no graph, and validates the parser/writer pipeline end-to-end with a real rule. The CLI command `nborder check file.ipynb` should already work and produce a useful diagnostic.

**Exit gate:** parser round-trips a corpus of 20+ real-world notebooks (pulled from popular ML/DS repos: scikit-learn examples, PyTorch tutorials, fastai courses, Kaggle kernels) byte-stably. NB101 fires correctly on a notebook with `[5, 3, 7]` execution counts and stays silent on a notebook with `[1, 2, 3, null, null]`. Golden round-trip suite is in CI.

---

## Phase 2 : Dataflow graph (days 5 to 9)

**Goal:** the cross-cell symbol graph that is nborder's core intellectual property.

Build the graph in three sub-passes. First, per-cell symbol extraction: for each cell, walk the LibCST tree and collect `SymbolDef` (assignments, function defs, class defs, imports, walrus operators, for-loop targets, with-as bindings, except-as bindings, comprehension targets that escape via `_`-style leaks) and `SymbolUse` (every name reference that isn't a definition). Handle the gnarly cases explicitly: augmented assignment (`x += 1` is both a use and a def), tuple unpacking (`a, b = ...` defines both), starred unpacking (`a, *rest = ...`), nested function scopes (a function body's locals don't leak), class body scopes (class-level names are attributes, not module names).

Second, symbol resolution across cells: for each `SymbolUse` in cell N, search backwards through cells N-1, N-2, ..., 0 for the first `SymbolDef` with the matching name. If found, record an edge `cell N -> cell M`. If not found, mark the use as `unresolved` (this is what NB201 and NB102 fire on).

Third, papermill and tag handling: cells tagged `parameters` or `injected-parameters` are inserted at logical position -1 in the resolution order so their definitions are visible to all subsequent cells regardless of source position. Cells tagged `nborder:skip` are excluded from both definition and use extraction.

Special bindings from magics flow into the graph here too: `name = !ls` defines `name`; `%%capture out` defines `out`; `%load_ext autoreload` sets a flag on the notebook metadata that NB103 consults later.

The graph data structure is a `DataflowGraph` dataclass holding the cell list, a `dict[str, list[CellIndex]]` symbol-to-defining-cells map, a `dict[CellIndex, list[Edge]]` adjacency list, and a `list[UnresolvedUse]` for fast rule access. Add `topological_sort()` and `detect_cycle()` methods on the graph; both NB201's reorder fix and any future analysis will need them.

**Exit gate:** the graph correctly resolves symbols on a hand-built test corpus covering: simple linear notebooks, notebooks with redefinition, notebooks with parameter cells, notebooks with shell assignments, notebooks with magic-bound names, notebooks with augmented assignment, notebooks with nested function/class scopes that should NOT leak names. Direct unit tests on the graph module hit 95%+ coverage. The graph builds in under 50ms on a 100-cell notebook.

---

## Phase 3 : NB201 and NB102 (days 10 to 12)

**Goal:** the two rules that justify the project. Both ride on the graph from Phase 2 and are nearly free to add.

NB201 walks the graph's `unresolved_uses` list, partitions into "name is defined later in source order" (NB201 hit) vs "name is never defined" (becomes NB102 territory or is a builtin/import miss). Diagnostic message names the symbol, the use cell, and the defining cell: "Variable `df` used in cell 7 is only defined in cell 12. The notebook will fail on Restart-and-Run-All."

NB102 simulates source-order execution by walking cells 0 through N-1 and maintaining a "currently defined names" set. For each cell, mark it failing if any of its uses reference a name not in the set. After processing, add this cell's defs to the set. Builtins (`print`, `len`, `range`, the full `builtins` module) are pre-loaded into the set. Import side effects (an `import` defines the imported name) are handled via the graph.

NB201's `--fix=reorder` runs `DataflowGraph.topological_sort()`. If the graph is a DAG, reorder cells to satisfy dependencies and clear all execution counts. If the graph has a cycle (cell A defines `x` used by cell B which defines `y` used by cell A), the fix bails with a diagnostic explaining why automatic reordering can't help, and points the user at the cycle.

NB102 has no auto-fix. The diagnostic is the value; restructuring the notebook is a human decision.

**Exit gate:** both rules fire correctly on the fixture corpus, both stay silent on the boundary cases, NB201 reorder fix is byte-stable when applied to an already-correct notebook (it's a no-op in that case), reorder fix on a fixable case produces a notebook that NB102 then approves. End-to-end test: a notebook with both NB201 and NB102 violations, run `check --fix=reorder`, verify the output passes `check` clean.

---

## Phase 4 : NB103 with library-aware seed injection (days 13 to 15)

**Goal:** the most ML-targeted rule, which alone will get the project shared in ML communities.

Detection logic: scan imports in graph order, identify any import matching the registered RNG library set (`numpy`, `numpy.random`, `random`, `torch`, `tensorflow`, `jax`, `sklearn`), then walk forward through cells looking for the first call to a stochastic API of that library before any seed-setting call. The "first stochastic call" detection is library-specific (`np.random.rand` and `np.random.normal` count for numpy; `torch.randn` and `torch.rand` for torch; etc.) and lives in the rule's per-library probe table.

The fix consults the seed-injection table from the copilot-instructions and inserts a new cell at logical position 0 (or after the parameters cell if one exists) with the appropriate seed-setting code. JAX gets a diagnostic-only treatment; sklearn gets a diagnostic-only treatment with guidance to use `random_state` per estimator.

Configuration lands here too: `[tool.nborder.seeds]` with `value = 42` (default) and `libraries = ["numpy", "torch"]` (subset selection if users want to opt out of TF detection, etc.).

**Exit gate:** NB103 fires correctly on notebooks using each supported RNG library, the seed injection produces syntactically valid code that LibCST can re-parse, the round-trip after seed injection is stable (running `check --fix=seeds` twice produces the same output as running it once), the JAX and sklearn diagnostic-only paths produce the documented messages.

---

## Phase 5 : Reporters and CLI polish (days 16 to 19)

**Goal:** the user-facing surface that determines whether anyone adopts the tool.

Build the text reporter first because it's what every adopter sees. Match ruff's diagnostic format closely: `path/to/notebook.ipynb:cell_3:7:5: NB201 Variable 'df' used before assignment`. Color via `rich` when stdout is a TTY, plain when not. Include a summary line at the bottom: "Found 4 errors. 2 fixable with --fix."

JSON reporter for CI: emit one diagnostic per object in a top-level array. Schema includes notebook path, cell index, cell ID, line, column, code, severity, message, fixable boolean, fix description.

GitHub Actions reporter: emit `::error file=...,col=...,endColumn=...::message` lines that GitHub renders as inline annotations on PR diffs. This is what makes the tool feel native in CI.

SARIF reporter is optional for v0.1; defer if time is tight, since SARIF is mainly for security-tool integrations.

CLI polish: implement `--diff` (using `difflib` to show what `--fix` would change without writing), `--output-format` flag dispatching to the right reporter, `--exit-zero` for users who want CI to not fail on findings, `nborder rule <code>` that prints the docs for a rule, `nborder config` that prints effective merged configuration.

**Exit gate:** running `nborder check examples/broken.ipynb` produces output that's visually indistinguishable from `ruff check` output in shape and density. JSON output is parseable. GitHub Actions output renders as inline annotations on a test PR. The CLI has `--help` text on every command and subcommand.

---

## Phase 6 : Pre-commit hook and GitHub Action (days 20 to 22)

**Goal:** the integrations that make the tool sticky.

Pre-commit hook lives in `.pre-commit-hooks.yaml` at the repo root. The hook runs `nborder check --fix` on staged `.ipynb` files. Test it by installing the hook into a sample repo and committing a broken notebook; the hook should auto-fix or block per the user's configuration.

GitHub Action lives in `action.yml` at the repo root. The action runs `nborder check --output-format=github` and exits non-zero on findings, which fails the workflow. Provide example workflow YAML in the README that adopters can copy. Include inputs for `path`, `fix` (boolean), and `select` (rule subset).

Publish the action to the GitHub Marketplace under the `code-quality` category.

**Exit gate:** pre-commit hook works against a real test repo, GitHub Action fires correctly on a PR in a test repo and renders inline annotations, both integrations are documented in the README with copy-pasteable examples.

---

## Phase 7 : Documentation and 0.1.0 release (days 23 to 28)

**Goal:** docs that let an adopter go from `pip install` to a working CI integration without asking questions.

README structure follows the project's standard: title and one-line description, badges (PyPI version, CI status, Python versions, license), "What this catches" with a 4-row table of the rules and a one-sentence example of each, quick start (install + run on a single notebook), pre-commit setup, GitHub Actions setup, configuration reference, FAQ ("Why not use ruff for this?", "How is this different from nbqa?", "Does this work with Polyglot/R/Julia?"), contributing pointer, license.

Per-rule docs live under `docs/rules/NB101.md` etc. Each page has: what it detects, why it matters, a bad example notebook (linked or inlined), a good example, the auto-fix behavior if any, configuration knobs, related rules.

Configuration reference is auto-generated from the dataclass schema. Single source of truth, no drift between code and docs.

Tag and release: bump version to 0.1.0 in `pyproject.toml` and `__init__.py`, update `CHANGELOG.md`, tag `v0.1.0`, push, GitHub Action builds and uploads to PyPI on tag push.

**Exit gate:** v0.1.0 is on PyPI, the README renders correctly on GitHub and PyPI, all four rules have docs pages, the test repo (set up in Phase 6) runs `pip install nborder` and uses the released package successfully end-to-end.

---

## Phase 8 : Launch and first-week response (days 29 to 35)

**Goal:** turn the release into visibility.

Announce on dev.to with a post explaining the bug class, the academic backing (Pimentel 2019, Quaranta 2022), the existing-tool gap, and the four rules with examples. Use the dev.to skill rules: human voice, no AI tells, evidence-backed claims only.

Cross-post to LinkedIn, X, and r/datascience / r/MachineLearning / r/Python on Reddit. Match each platform's register; don't copy-paste the dev.to post into LinkedIn verbatim.

Submit to Show HN if the early response on dev.to and Reddit suggests there's interest. HN front page is unpredictable, so don't over-invest, but a Show HN post for a notebook tool aimed at data scientists has a non-trivial chance of catching air.

Watch GitHub issues hourly for the first 48 hours. Bug reports in this window are gold; they're from the people who actually tried the tool. Triage immediately, fix critical issues within 24 hours, ship a 0.1.1 if anything material is broken.

After week 1, set a weekly cadence: Monday triage, Wednesday code, Friday release if anything's ready.

**Exit gate:** v0.1.0 has been live for 7 days, has at least one external issue or PR (sign of real-world adoption), has a public dev.to post with non-zero engagement, and has been linked from at least one Reddit thread or tweet by someone other than the author.

---

## Risk register

These are the failures most likely to derail the build. Each has a mitigation built into the plan; flagging them explicitly so they don't get rationalized away mid-project.

**Risk: byte-stable round-trip is harder than expected and eats Phase 1.** Mitigation: the golden test exists from day one; if it's failing, that's the first thing fixed before any other Phase 1 work continues. Don't ship a parser that round-trips most notebooks; ship a parser that round-trips all notebooks in the test corpus.

**Risk: the dataflow graph encounters a cell pattern the design didn't anticipate.** Mitigation: build the test corpus from real notebooks pulled from popular repos before writing the graph. Patterns that show up in scikit-learn's examples are patterns that have to work.

**Risk: NB103 false-positives on notebooks that set seeds in ways the detector misses (e.g., reading from a config file).** Mitigation: ship NB103 with a `# nborder: noqa: NB103` comment escape hatch from day one. False positives on a stochastic-detection rule are inevitable; the question is whether users can suppress them quickly.

**Risk: someone releases a competing tool during the build.** Mitigation: the differentiator is the dataflow graph; even if a static linter ships first, replicating the graph correctly is at least 2 to 3 weeks of work. Stay heads-down on Phase 2 and don't get distracted.

**Risk: time budget overruns.** Mitigation: every phase has a "ship the next phase even if this one isn't perfect" cut line. NB101 alone with byte-stable round-trip and a pre-commit hook is already shippable as v0.0.x and demonstrates real value; don't hold the whole release for NB103's sklearn handling.

---

## What success looks like

A v0.1.0 release on PyPI, used by at least 3 external repos within 30 days, with a GitHub stars trajectory above pynblint's lifetime total (45 stars) within 60 days. If the tool gets to 100 stars in 90 days, the moat is real and the path to v1.0 is clear. If it doesn't, the post-mortem question is whether the differentiator was actually understood by adopters or whether the messaging needs to lead harder with the dataflow-graph aspect.

The non-stars success metric: a single screenshot or thread of someone saying "nborder caught a bug that ruff missed and saved my afternoon." That's the artifact that converts viewers to users.
