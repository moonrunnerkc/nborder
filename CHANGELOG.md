# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.1] - 2026-04-26

### Fixed

- Reject invalid notebook paths, empty directory scans, and unknown `--include` levels instead of silently doing no work.
- Print clean CLI errors for missing and unparseable notebooks instead of tracebacks.
- Report the actual seed-cell insertion position in `--fix=seeds` outcomes.
- Remove the non-functional GitHub Action `select` input until rule selection lands in v0.2.
- Remove the unused `reproduce` extra and docs references until the fresh-kernel runner exists.
- Enforce coverage collection in CI and align contributor setup docs with `uv`.

## [0.1.0] - 2026-04-26

Initial public release.

### Added

- **NB101**: detection of non-monotonic execution counts. Auto-fix clears `execution_count` to `null` on every code cell.
- **NB102**: detection of names used in source order that no cell in the notebook defines. Diagnostic only; the user has to add the missing definition.
- **NB201**: detection of use-before-assign across cells. Auto-fix topologically sorts cells when the dependency graph is a DAG; bails on cycles with a message that names the symbols forming the cycle.
- **NB103**: detection of stochastic library APIs used before any seed call. Auto-fix injects a single seed cell with library-appropriate calls for `numpy`, `random`, `torch` (with optional `cuda` plumbing), and `tensorflow`. `jax` and `sklearn` are diagnostic-only.
- **Byte-stable round-trip writer**: `nborder check --fix` on a clean notebook produces a file whose JSON bytes are identical to the input. Asserted via `filecmp.cmp(original, rewritten, shallow=False)` against v4.0, v4.4, and v4.5 fixtures.
- **Cross-cell dataflow graph**: `SymbolDef`, `SymbolUse`, and `ImportBinding` records, deterministic topological sort, and cycle detection. Used by every NB1xx and NB2xx rule.
- **Magic and shell stripping**: line magics (`%name`), cell magics (`%%name`), shell escapes (`!ls`), shell-assignment forms (`files = !ls`), help syntax (`name?`), and IPython auto-call prefixes are stripped to typed metadata before LibCST parsing. `%%capture out` records the binding it creates.
- **Papermill conventions**: cells tagged `parameters` or `injected-parameters` define names at logical position zero in the dataflow graph. Cells tagged `nborder:skip` are excluded from analysis.
- **`# nborder: noqa` suppression**: bare form suppresses all rules in the cell; `# nborder: noqa: NB201,NB102` suppresses listed codes.
- **Pre-commit hook**: `.pre-commit-hooks.yaml` for adopters to register the `nborder` hook in their own repos.
- **GitHub Action**: composite `action.yml` runs `nborder check --output-format=github` with optional `--fix` and `--select` inputs. Branding: `check-circle` icon, green colour.
- **Reporters**: `text` (ruff-style with optional ANSI colour), `json` (stable schema), `github` (workflow commands), and `sarif` (validates against the SARIF 2.1.0 schema).
- **CLI flags**: `--fix`, `--diff`, `--output-format`, `--exit-zero`, `--include`. Subcommands: `check`, `rule <CODE>`, `config`.
- **Configuration**: `[tool.nborder.seeds]` in `pyproject.toml` controls the seed value and the enabled library set.

[0.1.1]: https://github.com/moonrunnerkc/nborder/releases/tag/v0.1.1
[0.1.0]: https://github.com/moonrunnerkc/nborder/releases/tag/v0.1.0
