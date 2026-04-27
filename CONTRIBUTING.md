# Contributing to nborder

Thanks for considering a contribution. nborder is small enough that the bar to add a rule or a fix is one PR with tests and a docs page.

## Set up the dev environment

```bash
git clone https://github.com/moonrunnerkc/nborder
cd nborder
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
```

The `[dev]` extra installs `mypy`, `pytest`, `pytest-cov`, `ruff`, `pre-commit`, and `jsonschema`.

## Run the checks

```bash
pytest                   # full test suite
ruff check src tests     # lint
mypy                     # strict type-check src/
```

CI runs the same three checks plus a self-test that runs `nborder check tests/fixtures/roundtrip` to catch regressions in our own fixtures. Run all three locally before opening a PR.

## Add a rule

Each rule needs five things:

1. A registry entry. Rule codes are stable forever; pick the next free code in the relevant block (`NB1xx` ordering, `NB2xx` dataflow, `NB3xx` imports, etc.).
2. A rule module under `src/nborder/rules/<code>.py` that consumes the dataflow graph and emits `Diagnostic` objects.
3. At least three fixture notebooks under `tests/fixtures/<CODE>/`: one that triggers the rule, one boundary case that almost-but-not-quite triggers it, and one with the fix already applied that should be a no-op on round-trip.
4. Tests under `tests/test_<code>.py`. Names describe behaviour, not wiring (`test_rule_fires_on_X`, not `test_check_calls_visit_Y`).
5. A docs page under `docs/rules/<CODE>.md`. Match the structure of the existing pages: title, what it catches, why it matters, bad example, good example, auto-fix behaviour, configuration, related rules.

If the rule has an associated fix, the fix lives under `src/nborder/fix/` and consumes the diagnostic's `FixDescriptor`. The fix must be idempotent: running it twice produces a byte-identical second output.

## Code style

- See [`./.github/copilot-instructions.md`](./.github/copilot-instructions.md) for the full coding conventions.
- 300-line hard cap per file. If a module hits 250, split it along natural seams.
- Frozen slotted dataclasses for value objects (`Cell`, `SymbolDef`, `Diagnostic`, `FixDescriptor`).
- No bare `Any`. No em dashes anywhere. No generic variable names (`data`, `result`, `temp`).
- Errors include both what failed and what the user should do next.

## Commit messages

Conventional-commits-ish:

- `feat:` user-facing additions
- `fix:` bug fixes
- `refactor:` no behaviour change
- `docs:` documentation only
- `test:` test-only changes
- `chore:` housekeeping

Add a scope when it clarifies (`feat(nb103): ...`). The body should explain *why* the change matters, not just what it does.

## Pull request checklist

Before opening a PR:

- [ ] `pytest` passes; no skipped tests except those gated on optional extras.
- [ ] `ruff check src tests` is clean.
- [ ] `mypy` is clean.
- [ ] `nborder check tests/fixtures/roundtrip` passes.
- [ ] New rules ship with at least three fixture notebooks and a docs page.
- [ ] `CHANGELOG.md` has an entry under `## [Unreleased]` describing the change in adopter-facing terms.

If the PR adds a fix, include a before/after diff of a real fixture notebook in the description so reviewers can sanity-check the transformation visually.
