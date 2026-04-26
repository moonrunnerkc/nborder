from __future__ import annotations

from pathlib import Path

from nborder.graph.builder import build_dataflow_graph
from nborder.parser.reader import read_notebook
from nborder.rules.nb201 import check_use_before_assign
from nborder.rules.unresolved import classify_unresolved_uses

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_nb201_flags_use_defined_later_in_source_order() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "NB201" / "use_df_later_def.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)

    diagnostics = check_use_before_assign(notebook, graph, classified_uses)

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.code == "NB201"
    assert diagnostic.severity == "error"
    assert diagnostic.cell_index == 0
    assert diagnostic.cell_id == "use-df"
    assert diagnostic.line == 1
    assert diagnostic.column == 7
    assert diagnostic.fixable is True
    assert diagnostic.fix_descriptor is not None
    assert diagnostic.fix_descriptor.fix_id == "reorder"
    assert diagnostic.fix_descriptor.target_cells == [0, 1]


def test_nb201_emits_one_diagnostic_per_broken_reference() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "mixed.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)

    diagnostics = check_use_before_assign(notebook, graph, classified_uses)

    assert [diagnostic.message for diagnostic in diagnostics] == [
        "Variable `df` used in cell 0 is only defined in cell 1. "
        "The notebook will fail on Restart-and-Run-All."
    ]


def test_nb201_ignores_papermill_parameter_cell_later_in_source_order() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "parameters_late.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)

    diagnostics = check_use_before_assign(notebook, graph, classified_uses)

    assert diagnostics == ()


def test_nb201_ignores_skipped_cells() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "skip_name_error.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)

    diagnostics = check_use_before_assign(notebook, graph, classified_uses)

    assert diagnostics == ()
