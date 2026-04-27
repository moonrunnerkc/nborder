from __future__ import annotations

import sys
import time
from pathlib import Path

import libcst as cst
import pytest
from nbformat.notebooknode import NotebookNode

from nborder.graph.builder import build_dataflow_graph
from nborder.graph.models import CellSymbols, DataflowGraph, Edge
from nborder.parser.magics import strip_magics
from nborder.parser.models import Cell, Notebook
from nborder.parser.reader import read_notebook

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_dataflow_graph_resolves_to_most_recent_prior_definition() -> None:
    notebook = _notebook_from_sources(("df = first", "df = second", "print(df)"))

    graph = build_dataflow_graph(notebook)

    df_edges = [edge for edge in graph.adjacency[2] if edge.symbol == "df"]
    assert df_edges == [Edge(source_cell=2, target_cell=1, symbol="df")]


def test_dataflow_graph_resolves_parameter_cells_from_logical_start() -> None:
    notebook = _notebook_from_sources(
        ("print(input_path)", "input_path = 'input.csv'"),
        tags_by_cell={1: frozenset({"parameters"})},
    )

    graph = build_dataflow_graph(notebook)

    assert Edge(source_cell=0, target_cell=1, symbol="input_path") in graph.adjacency[0]
    assert graph.unresolved_uses == []


def test_dataflow_graph_excludes_skipped_cells_from_extraction() -> None:
    notebook = _notebook_from_sources(
        ("hidden_name = 1", "print(hidden_name)"),
        tags_by_cell={0: frozenset({"nborder:skip"})},
    )

    graph = build_dataflow_graph(notebook)

    assert graph.symbol_to_defining_cells == {}
    assert [unresolved.symbol.name for unresolved in graph.unresolved_uses] == ["hidden_name"]


def test_dataflow_graph_resolves_magic_bindings_from_parser_records() -> None:
    notebook = _notebook_from_sources(
        ("files = !ls *.csv\nprint(files)", "%%capture captured\nprint('x')")
    )

    graph = build_dataflow_graph(notebook)
    first_cell_definitions = {
        definition.name for definition in graph.symbols_by_cell[0].definitions
    }
    second_cell_definitions = {
        definition.name for definition in graph.symbols_by_cell[1].definitions
    }

    assert "files" in first_cell_definitions
    assert "captured" in second_cell_definitions


def test_dataflow_graph_tracks_wildcard_import_cells_for_later_rules() -> None:
    notebook = _notebook_from_sources(("from math import *", "print(sqrt(4))"))

    graph = build_dataflow_graph(notebook)

    assert graph.wildcard_import_cells == frozenset({0})
    assert Edge(source_cell=1, target_cell=0, symbol="sqrt") in graph.adjacency[1]


def test_dataflow_graph_does_not_import_user_modules_for_wildcards(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    module_dir = tmp_path / "evil_pkg"
    module_dir.mkdir()
    side_effect_path = tmp_path / "imported.txt"
    module_dir.joinpath("__init__.py").write_text(
        f"from pathlib import Path\nPath({str(side_effect_path)!r}).write_text('imported')\n",
        encoding="utf-8",
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    notebook = _notebook_from_sources(("from evil_pkg import *\nprint(stolen_name)",))

    graph = build_dataflow_graph(notebook)

    assert not side_effect_path.exists()
    assert graph.wildcard_import_cells == frozenset({0})
    assert [unresolved.symbol.name for unresolved in graph.unresolved_uses] == ["stolen_name"]


def test_dataflow_graph_records_duplicate_cell_definitions_once_in_symbol_index() -> None:
    notebook = _notebook_from_sources(("value = 1\nvalue = 2",))

    graph = build_dataflow_graph(notebook)

    assert graph.symbol_to_defining_cells == {"value": [0]}


def test_dataflow_graph_silences_same_cell_self_assignment() -> None:
    notebook = _notebook_from_sources(
        ("input_path = input_path",),
        tags_by_cell={0: frozenset({"parameters"})},
    )

    graph = build_dataflow_graph(notebook)

    assert graph.unresolved_uses == []


def test_topological_sort_returns_dependency_first_order() -> None:
    graph = _manual_graph(
        (
            Edge(source_cell=2, target_cell=0, symbol="a"),
            Edge(source_cell=2, target_cell=1, symbol="b"),
        )
    )

    assert graph.topological_sort() == [0, 1, 2]


def test_topological_sort_ignores_self_edges() -> None:
    graph = _manual_graph((Edge(source_cell=1, target_cell=1, symbol="same_cell"),))

    assert graph.topological_sort() == [0, 1, 2]


def test_topological_sort_returns_none_when_cycle_exists() -> None:
    graph = _manual_graph(
        (
            Edge(source_cell=0, target_cell=1, symbol="right"),
            Edge(source_cell=1, target_cell=0, symbol="left"),
        )
    )

    assert graph.topological_sort() is None


def test_detect_cycle_returns_cells_participating_in_cycle() -> None:
    graph = _manual_graph(
        (
            Edge(source_cell=0, target_cell=1, symbol="right"),
            Edge(source_cell=1, target_cell=0, symbol="left"),
        )
    )

    assert graph.detect_cycle() == [0, 1]


def test_detect_cycle_returns_empty_list_for_dag() -> None:
    graph = _manual_graph((Edge(source_cell=2, target_cell=1, symbol="previous"),))

    assert graph.detect_cycle() == []


def test_real_world_fixture_corpus_builds_graph_without_crashing() -> None:
    fixture_paths = sorted((FIXTURE_ROOT / "real_world").glob("*.ipynb"))

    for fixture_path in fixture_paths:
        notebook = read_notebook(fixture_path)
        build_dataflow_graph(notebook)


def test_dataflow_graph_builds_100_cell_notebook_under_50ms() -> None:
    source_texts = tuple(
        "value_0 = 0"
        if cell_number == 0
        else f"value_{cell_number} = value_{cell_number - 1} + 1"
        for cell_number in range(100)
    )
    notebook = _notebook_from_sources(source_texts)

    started_at = time.perf_counter()
    build_dataflow_graph(notebook)
    elapsed_ms = (time.perf_counter() - started_at) * 1000
    max_elapsed_ms = 200 if sys.gettrace() is not None else 50

    assert elapsed_ms < max_elapsed_ms


def _code_cell(index: int, source_text: str, tags: frozenset[str] = frozenset()) -> Cell:
    magic_strip = strip_magics(source_text)
    cst_module = cst.parse_module(magic_strip.stripped_source)
    return Cell(
        index=index,
        cell_id=f"cell-{index}",
        kind="code",
        source=source_text,
        stripped_source=magic_strip.stripped_source,
        tags=tags,
        execution_count=None,
        magics=magic_strip.magics,
        cst_module=cst_module,
    )


def _notebook_from_sources(
    source_texts: tuple[str, ...],
    tags_by_cell: dict[int, frozenset[str]] | None = None,
) -> Notebook:
    tag_map = tags_by_cell or {}
    cells = tuple(
        _code_cell(index, source_text, tag_map.get(index, frozenset()))
        for index, source_text in enumerate(source_texts)
    )
    return Notebook(
        path=Path("test.ipynb"),
        raw_bytes=b"",
        node=NotebookNode(),
        nbformat_minor=5,
        cells=cells,
    )


def _manual_graph(edges: tuple[Edge, ...]) -> DataflowGraph:
    cells = tuple(_code_cell(index, "") for index in range(3))
    adjacency: dict[int, list[Edge]] = {cell.index: [] for cell in cells}
    for edge in edges:
        adjacency[edge.source_cell].append(edge)
    return DataflowGraph(
        cells=cells,
        symbol_to_defining_cells={},
        adjacency=adjacency,
        unresolved_uses=[],
        symbols_by_cell={cell.index: CellSymbols(cell.index, (), (), (), False) for cell in cells},
        wildcard_import_cells=frozenset(),
    )
