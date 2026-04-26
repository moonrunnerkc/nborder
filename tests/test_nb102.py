from __future__ import annotations

from pathlib import Path

from nborder.graph.builder import build_dataflow_graph
from nborder.parser.reader import read_notebook
from nborder.rules.nb102 import check_restart_run_all
from nborder.rules.unresolved import classify_unresolved_uses

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_nb102_flags_name_never_defined_in_notebook() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "NB102" / "undefined_name.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)

    diagnostics = check_restart_run_all(notebook, graph, classified_uses)

    assert len(diagnostics) == 1
    diagnostic = diagnostics[0]
    assert diagnostic.code == "NB102"
    assert diagnostic.severity == "error"
    assert diagnostic.cell_index == 0
    assert diagnostic.cell_id == "undefined-name"
    assert diagnostic.line == 1
    assert diagnostic.column == 7
    assert diagnostic.fixable is False
    assert diagnostic.fix_descriptor is None


def test_nb102_keeps_mixed_undefined_name_separate_from_nb201() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "mixed.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)

    diagnostics = check_restart_run_all(notebook, graph, classified_uses)

    assert [diagnostic.message for diagnostic in diagnostics] == [
        "Name `totally_undefined` is used in cell 0 but never defined in the notebook."
    ]


def test_nb102_reports_wildcard_coverage_as_info_when_requested() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "wildcard.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)

    diagnostics = check_restart_run_all(notebook, graph, classified_uses)

    assert len(diagnostics) == 1
    assert diagnostics[0].severity == "info"
    assert diagnostics[0].message.startswith("Possibly defined by wildcard import from numpy: ")


def test_nb102_hides_wildcard_coverage_when_not_requested() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "wildcard.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)

    diagnostics = check_restart_run_all(
        notebook,
        graph,
        classified_uses,
        include_wildcard_info=False,
    )

    assert diagnostics == ()


def test_nb102_ignores_skipped_cells() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "phase3" / "skip_name_error.ipynb")
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)

    diagnostics = check_restart_run_all(notebook, graph, classified_uses)

    assert diagnostics == ()
