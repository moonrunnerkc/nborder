from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

from nborder.fix.pipeline import plan_fix_pipeline
from nborder.graph.builder import build_dataflow_graph
from nborder.parser.reader import read_notebook
from nborder.parser.writer import write_notebook
from nborder.rules.nb201 import check_use_before_assign
from nborder.rules.unresolved import classify_unresolved_uses

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_writer_preserves_clean_notebook_bytes(tmp_path: Path) -> None:
    for fixture_path in sorted((FIXTURE_ROOT / "roundtrip").glob("*.ipynb")):
        copied_notebook = tmp_path / fixture_path.name
        shutil.copyfile(fixture_path, copied_notebook)

        notebook = read_notebook(copied_notebook)
        write_notebook(notebook)

        assert filecmp.cmp(fixture_path, copied_notebook, shallow=False)


def test_writer_preserves_real_world_notebook_bytes(tmp_path: Path) -> None:
    for fixture_path in sorted((FIXTURE_ROOT / "real_world").glob("*.ipynb")):
        copied_notebook = tmp_path / fixture_path.name
        shutil.copyfile(fixture_path, copied_notebook)

        notebook = read_notebook(copied_notebook)
        write_notebook(notebook)

        assert filecmp.cmp(fixture_path, copied_notebook, shallow=False)


def test_writer_mutation_path_reorders_and_clears_counts_across_minor_versions(
    tmp_path: Path,
) -> None:
    for fixture_path in sorted((FIXTURE_ROOT / "phase3").glob("reorder_v*.ipynb")):
        copied_notebook = tmp_path / fixture_path.name
        shutil.copyfile(fixture_path, copied_notebook)

        notebook = read_notebook(copied_notebook)
        graph = build_dataflow_graph(notebook)
        classified_uses = classify_unresolved_uses(graph)
        diagnostics = check_use_before_assign(notebook, graph, classified_uses)
        cell_order, clear_counts, _outcomes = plan_fix_pipeline(
            notebook,
            graph,
            diagnostics,
            frozenset({"reorder"}),
        )
        write_notebook(notebook, cell_order=cell_order, clear_execution_counts=clear_counts)

        rewritten_notebook = read_notebook(copied_notebook)
        assert rewritten_notebook.nbformat_minor == notebook.nbformat_minor
        assert rewritten_notebook.cells[0].source == "df = {'rows': 3}\n"
        assert all(cell.execution_count is None for cell in rewritten_notebook.cells)

        first_fix_bytes = copied_notebook.read_bytes()
        graph = build_dataflow_graph(rewritten_notebook)
        classified_uses = classify_unresolved_uses(graph)
        diagnostics = check_use_before_assign(rewritten_notebook, graph, classified_uses)
        cell_order, clear_counts, _outcomes = plan_fix_pipeline(
            rewritten_notebook,
            graph,
            diagnostics,
            frozenset({"reorder"}),
        )
        write_notebook(
            rewritten_notebook,
            cell_order=cell_order,
            clear_execution_counts=clear_counts,
        )

        assert copied_notebook.read_bytes() == first_fix_bytes
