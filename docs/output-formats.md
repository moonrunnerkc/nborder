# Output formats

`nborder check` supports four output formats via `--output-format=text|json|github|sarif`. The default is `text`.

## text

Human-readable output styled after ruff. One diagnostic per line:

```
notebooks/example.ipynb:cell_3:7:5: NB201 Variable `df` used in cell 3 is only defined in cell 5. [*]
notebooks/example.ipynb:cell_3:9:1: NB103 NumPy random API used before a seed is set. [*]
notebooks/example.ipynb:cell_5:1:1: NB102 Name `undefined_var` is used in cell 5 but never defined in the notebook.

Found 3 errors. 2 fixable with --fix.
```

Notes:

- Path is rendered relative to the current working directory when possible, absolute otherwise.
- `cell_N` uses the 0-based cell index. Cell IDs are exposed only via the JSON output.
- Line and column are 1-based and refer to the position inside the cell, matching ruff's convention.
- A trailing `[*]` marks fixable diagnostics.
- Color is enabled when stdout is a TTY and disabled otherwise.

When `--fix` is requested, a `Fix outcomes:` block precedes the summary, listing each pipeline stage and its outcome.

## json

Stable, machine-readable shape for CI consumption. The top-level object always has two keys:

```json
{
  "diagnostics": [
    {
      "notebook_path": "notebooks/example.ipynb",
      "cell_index": 3,
      "cell_id": "abc123",
      "line": 7,
      "column": 5,
      "end_line": 7,
      "end_column": 12,
      "code": "NB201",
      "severity": "error",
      "message": "Variable `df` used in cell 3 is only defined in cell 5.",
      "fixable": true,
      "fix_id": "reorder"
    }
  ],
  "fix_outcomes": [
    {"fix_id": "reorder", "status": "applied", "details": "applied to 5 cells"}
  ]
}
```

Schema notes:

- `severity` is one of `"error"`, `"warning"`, `"info"`.
- `fix_id` is `null` when the diagnostic is not fixable.
- `cell_id` is `null` when the source notebook does not record one (older nbformat versions).
- `fix_outcomes` is `null` when `--fix` was not requested. When present, each entry has `fix_id`, `status` (one of `"applied"`, `"bailed"`, `"no-op"`), and `details`.

## github

GitHub Actions workflow commands suitable for inline annotations:

```
::error file=notebooks/example.ipynb,line=7,col=5,endLine=7,endColumn=12,title=NB201::Variable `df` used in cell 3 is only defined in cell 5.
::warning file=notebooks/example.ipynb,line=9,col=1,endLine=9,endColumn=8,title=NB103::NumPy random API used before a seed is set.
::notice file=notebooks/example.ipynb,line=1,col=1,endLine=1,endColumn=1,title=NB102::Possibly defined by wildcard import from numpy: ...
```

Severity mapping: `error` to `::error`, `warning` to `::warning`, `info` to `::notice`. The `info` level is hidden by default; pass `--include=info` to surface it.

Line numbers are cell-relative (line 1 is the first line inside the cell), which is a known limitation documented in `docs/known-limitations.md`.

## sarif

SARIF 2.1.0 JSON, hand-rolled to avoid extra dependencies. The output validates against the official `sarif-schema-2.1.0.json` schema. SARIF is consumable by GitHub's code scanning ingest, Azure DevOps, and many other static-analysis dashboards.

Each rule (NB101, NB102, NB201, NB103) appears in `runs[0].tool.driver.rules` with `id`, `name`, `shortDescription`, `fullDescription`, and `helpUri`. Each diagnostic appears in `runs[0].results` with `ruleId`, `level`, `message.text`, and a single `locations` entry pointing at the notebook file and line range.
