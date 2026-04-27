"""Round-trip determinism tests for NB103 seed injection.

These tests prove that ``nborder check --fix`` produces notebooks whose
executed outputs are byte-identical across runs. They spin up a real
Jupyter kernel via ``nbclient`` and are gated behind ``--run-slow``.

The legacy NumPy fix bug (TD-A1) silently shipped a fix that did not seed
the legacy ``np.random`` global state. The static checker accepted the
result on a re-pass and reported success, but two executions of the
'fixed' notebook produced different outputs. The test below proves that
the fix layer now seeds both APIs and that two kernel executions of the
fixed notebook produce identical stdout.
"""

from __future__ import annotations

from pathlib import Path

import nbformat
import pytest
from typer.testing import CliRunner

from nborder.cli import app

pytest.importorskip(
    "nbclient",
    reason="nbclient is only required when running the slow determinism suite",
)
from nbclient import NotebookClient  # noqa: E402


def _execute_text_outputs(notebook_path: Path) -> str:
    """Execute a notebook with a fresh kernel and return concatenated stdout text."""
    notebook = nbformat.read(str(notebook_path), as_version=4)
    NotebookClient(notebook, timeout=60, kernel_name="python3").execute()
    text_chunks: list[str] = []
    for cell in notebook.cells:
        for output in cell.get("outputs", []):
            text = output.get("text")
            if text:
                text_chunks.append(text)
    return "\n".join(text_chunks)


def _write_notebook(path: Path, sources: list[str]) -> None:
    notebook = nbformat.v4.new_notebook()
    notebook.cells = [nbformat.v4.new_code_cell(source) for source in sources]
    nbformat.write(notebook, str(path))


@pytest.mark.slow
def test_numpy_legacy_rand_produces_byte_identical_reruns_after_fix(
    tmp_path: Path,
) -> None:
    notebook_path = tmp_path / "numpy_legacy_rand.ipynb"
    _write_notebook(
        notebook_path,
        [
            "import numpy as np",
            "values = np.random.rand(3)\nprint(values.tolist())",
        ],
    )

    fix_outcome = CliRunner().invoke(
        app, ["check", "--fix-categories=seeds", str(notebook_path)]
    )
    assert "seeds: applied" in fix_outcome.output, fix_outcome.output

    first_run = _execute_text_outputs(notebook_path)
    second_run = _execute_text_outputs(notebook_path)
    assert first_run == second_run, (
        f"reruns differed:\nfirst:  {first_run!r}\nsecond: {second_run!r}"
    )
    assert first_run.strip(), "expected stdout from the fixed notebook"


@pytest.mark.slow
def test_numpy_legacy_randint_and_randn_are_deterministic_after_fix(
    tmp_path: Path,
) -> None:
    notebook_path = tmp_path / "numpy_legacy_randint_randn.ipynb"
    _write_notebook(
        notebook_path,
        [
            "import numpy as np",
            (
                "ints = np.random.randint(0, 100, size=4)\n"
                "norms = np.random.randn(3)\n"
                "print(ints.tolist(), norms.tolist())"
            ),
        ],
    )

    fix_outcome = CliRunner().invoke(
        app, ["check", "--fix-categories=seeds", str(notebook_path)]
    )
    assert "seeds: applied" in fix_outcome.output, fix_outcome.output

    first_run = _execute_text_outputs(notebook_path)
    second_run = _execute_text_outputs(notebook_path)
    assert first_run == second_run, (
        f"reruns differed:\nfirst:  {first_run!r}\nsecond: {second_run!r}"
    )


@pytest.mark.slow
def test_stdlib_random_produces_byte_identical_reruns_after_fix(
    tmp_path: Path,
) -> None:
    notebook_path = tmp_path / "stdlib_random.ipynb"
    _write_notebook(
        notebook_path,
        [
            "import random",
            "values = [random.random() for _ in range(3)]\nprint(values)",
        ],
    )

    fix_outcome = CliRunner().invoke(
        app, ["check", "--fix-categories=seeds", str(notebook_path)]
    )
    assert "seeds: applied" in fix_outcome.output, fix_outcome.output

    first_run = _execute_text_outputs(notebook_path)
    second_run = _execute_text_outputs(notebook_path)
    assert first_run == second_run, (
        f"reruns differed:\nfirst:  {first_run!r}\nsecond: {second_run!r}"
    )
