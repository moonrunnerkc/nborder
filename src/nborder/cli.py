from __future__ import annotations

import difflib
from pathlib import Path
from typing import Annotated

import typer

from nborder.config import Config, load_config
from nborder.fix.models import FixOutcome
from nborder.fix.pipeline import plan_fix_pipeline
from nborder.graph.builder import build_dataflow_graph
from nborder.parser.models import Notebook
from nborder.parser.reader import read_notebook
from nborder.parser.writer import serialize_notebook, write_notebook
from nborder.reporters.text import format_diagnostic, format_summary
from nborder.rules.nb101 import check_non_monotonic_execution_counts
from nborder.rules.nb102 import check_restart_run_all
from nborder.rules.nb103 import check_unseeded_stochastic_calls
from nborder.rules.nb201 import check_use_before_assign
from nborder.rules.suppression import filter_suppressed_diagnostics
from nborder.rules.types import Diagnostic
from nborder.rules.unresolved import classify_unresolved_uses

app = typer.Typer(
    help="Lint Jupyter notebooks for hidden-state and execution-order bugs.",
    context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
)


@app.callback()
def main() -> None:
    """Run the nborder command-line interface."""

@app.command(context_settings={"ignore_unknown_options": True, "allow_extra_args": True})
def check(
    paths: Annotated[
        list[str],
        typer.Argument(help="Notebook files, directories, and --fix tokens to check."),
    ],
    diff: Annotated[
        bool,
        typer.Option("--diff", help="Show safe-fix changes without writing files."),
    ] = False,
    include: Annotated[
        str | None,
        typer.Option("--include", help="Include optional diagnostic levels, such as info."),
    ] = None,
) -> None:
    """Check notebooks for hidden-state and execution-order bugs.

    Args:
        paths: Notebook files or directories to check, with manually parsed fix tokens.
        diff: Whether to print the safe-fix diff without writing.
        include: Optional diagnostic levels to include in output.
    """
    fix, parsed_paths = _parse_check_tokens(tuple(paths))
    notebooks = tuple(_iter_notebook_paths(parsed_paths))
    diagnostics: list[Diagnostic] = []
    fix_outcomes: list[FixOutcome] = []
    include_info = include == "info"
    enabled_fixes = _enabled_fixes(fix, diff)

    for notebook_path in notebooks:
        config = load_config(notebook_path)
        notebook = read_notebook(notebook_path)
        notebook_diagnostics = _check_notebook(notebook, config, include_info=include_info)

        if enabled_fixes:
            graph = build_dataflow_graph(notebook)
            (
                cell_order,
                seed_cell_source,
                clear_execution_counts,
                notebook_fix_outcomes,
            ) = plan_fix_pipeline(
                notebook,
                graph,
                notebook_diagnostics,
                enabled_fixes,
                config.seeds,
            )
            fix_outcomes.extend(notebook_fix_outcomes)
            if diff:
                _write_diff(notebook, cell_order, seed_cell_source, clear_execution_counts)
            elif cell_order is not None or seed_cell_source is not None or clear_execution_counts:
                write_notebook(
                    notebook,
                    cell_order=cell_order,
                    seed_cell_source=seed_cell_source,
                    clear_execution_counts=clear_execution_counts,
                )
                notebook = read_notebook(notebook_path)
                notebook_diagnostics = _check_notebook(notebook, config, include_info=include_info)

        diagnostics.extend(_visible_diagnostics(notebook_diagnostics, include_info=include_info))

    for diagnostic in diagnostics:
        typer.echo(format_diagnostic(diagnostic))

    if fix_outcomes:
        typer.echo(_format_fix_outcomes(tuple(fix_outcomes)))

    if diagnostics:
        typer.echo(format_summary(tuple(diagnostics)))
        raise typer.Exit(code=1)


def _parse_check_tokens(tokens: tuple[str, ...]) -> tuple[str | None, tuple[Path, ...]]:
    fix: str | None = None
    parsed_paths: list[Path] = []
    for token in tokens:
        if token == "--fix":
            fix = "all"
            continue
        if token.startswith("--fix="):
            fix = token.removeprefix("--fix=") or "all"
            continue
        parsed_paths.append(Path(token))
    return fix, tuple(parsed_paths)


def _iter_notebook_paths(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    notebook_paths: list[Path] = []
    for check_path in paths:
        if check_path.is_dir():
            notebook_paths.extend(sorted(check_path.rglob("*.ipynb")))
            continue
        if check_path.suffix == ".ipynb":
            notebook_paths.append(check_path)
    return tuple(notebook_paths)


def _check_notebook(
    notebook: Notebook,
    config: Config,
    *,
    include_info: bool,
) -> tuple[Diagnostic, ...]:
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)
    diagnostics = [
        *check_non_monotonic_execution_counts(notebook),
        *check_use_before_assign(notebook, graph, classified_uses),
        *check_unseeded_stochastic_calls(notebook, graph, config.seeds),
        *check_restart_run_all(
            notebook,
            graph,
            classified_uses,
            include_wildcard_info=include_info,
        ),
    ]
    return filter_suppressed_diagnostics(notebook, tuple(diagnostics))


def _visible_diagnostics(
    diagnostics: tuple[Diagnostic, ...],
    *,
    include_info: bool,
) -> tuple[Diagnostic, ...]:
    if include_info:
        return diagnostics
    return tuple(diagnostic for diagnostic in diagnostics if diagnostic.severity != "info")


def _enabled_fixes(fix: str | None, diff: bool) -> frozenset[str]:
    if diff:
        return frozenset({"reorder", "seeds", "clear-counts"})
    if fix is None:
        return frozenset()
    if fix == "all":
        return frozenset({"reorder", "seeds", "clear-counts"})
    return frozenset(fix_id.strip() for fix_id in fix.split(",") if fix_id.strip())


def _write_diff(
    notebook: Notebook,
    cell_order: tuple[int, ...] | None,
    seed_cell_source: str | None,
    clear_execution_counts: bool,
) -> None:
    modified_bytes = serialize_notebook(
        notebook,
        cell_order=cell_order,
        seed_cell_source=seed_cell_source,
        clear_execution_counts=clear_execution_counts,
    )
    if modified_bytes == notebook.raw_bytes:
        return
    typer.echo(f"Diff for {notebook.path}")
    original_lines = notebook.raw_bytes.decode("utf-8").splitlines(keepends=True)
    modified_lines = modified_bytes.decode("utf-8").splitlines(keepends=True)
    for diff_line in difflib.unified_diff(
        original_lines,
        modified_lines,
        fromfile=str(notebook.path),
        tofile=str(notebook.path),
    ):
        typer.echo(diff_line, nl=False)


def _format_fix_outcomes(fix_outcomes: tuple[FixOutcome, ...]) -> str:
    lines = ["Fix outcomes:"]
    for fix_outcome in fix_outcomes:
        lines.append(f"  {fix_outcome.fix_id}: {fix_outcome.status} ({fix_outcome.description})")
    return "\n".join(lines)
