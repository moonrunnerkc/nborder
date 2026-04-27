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
from nborder.parser.reader import NotebookParseError, read_notebook
from nborder.parser.writer import serialize_notebook, write_notebook
from nborder.reporters.base import Reporter
from nborder.reporters.github import GithubReporter
from nborder.reporters.jsonout import JsonReporter
from nborder.reporters.sarif import SarifReporter
from nborder.reporters.text import TextReporter
from nborder.rules.nb101 import check_non_monotonic_execution_counts
from nborder.rules.nb102 import check_restart_run_all
from nborder.rules.nb103 import check_unseeded_stochastic_calls
from nborder.rules.nb201 import check_use_before_assign
from nborder.rules.suppression import filter_suppressed_diagnostics
from nborder.rules.types import Diagnostic, Severity
from nborder.rules.unresolved import classify_unresolved_uses

_DEFAULT_INCLUDE_LEVELS: frozenset[Severity] = frozenset({"error", "warning"})

_RULE_DOCS_DIR = Path(__file__).parent.parent.parent / "docs" / "rules"

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
        list[str], typer.Argument(help="Notebook files, directories, and --fix tokens.")
    ],
    diff: Annotated[bool, typer.Option("--diff", help="Show safe-fix changes.")] = False,
    include: Annotated[
        str | None,
        typer.Option(
            "--include",
            help="Diagnostic levels to include (error, warning, info). Comma-separated.",
        ),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option(
            "--output-format",
            help="Output format: text (default), json, github, or sarif.",
        ),
    ] = "text",
    exit_zero: Annotated[
        bool, typer.Option("--exit-zero", help="Exit 0 with diagnostics.")
    ] = False,
) -> None:
    """Check notebooks for hidden-state and execution-order bugs."""
    fix, parsed_paths = _parse_check_tokens(tuple(paths))
    notebooks = tuple(_iter_notebook_paths(parsed_paths))
    include_levels = _parse_include(include)
    enabled_fixes = _enabled_fixes(fix, diff)
    reporter = _select_reporter(output_format)

    diagnostics: list[Diagnostic] = []
    fix_outcomes: list[FixOutcome] = []

    for notebook_path in notebooks:
        try:
            config = load_config(notebook_path)
            notebook = read_notebook(notebook_path)
            notebook_diagnostics = _check_notebook(notebook, config, include_levels=include_levels)

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
                elif (
                    cell_order is not None
                    or seed_cell_source is not None
                    or clear_execution_counts
                ):
                    write_notebook(
                        notebook,
                        cell_order=cell_order,
                        seed_cell_source=seed_cell_source,
                        clear_execution_counts=clear_execution_counts,
                    )
                    notebook = read_notebook(notebook_path)
                    notebook_diagnostics = _check_notebook(
                        notebook, config, include_levels=include_levels
                    )

            diagnostics.extend(
                _visible_diagnostics(notebook_diagnostics, include_levels=include_levels)
            )
        except NotebookParseError as parse_error:
            typer.echo(f"error: {notebook_path}: {parse_error}", err=True)
            raise typer.Exit(code=2) from parse_error
        except FileNotFoundError as missing_file:
            failed_path = missing_file.filename or notebook_path
            typer.echo(
                f"error: {failed_path}: file not found; pass an existing notebook or directory.",
                err=True,
            )
            raise typer.Exit(code=2) from missing_file

    visible_fix_outcomes = tuple(fix_outcomes) if enabled_fixes else None
    rendered_output = reporter.report(tuple(diagnostics), visible_fix_outcomes)
    if rendered_output:
        typer.echo(rendered_output)

    if diagnostics and not exit_zero:
        raise typer.Exit(code=1)


@app.command()
def rule(rule_code: Annotated[str, typer.Argument(help="Rule code (e.g., NB101).")]) -> None:
    """Print documentation for a single rule."""
    rule_path = _RULE_DOCS_DIR / f"{rule_code.upper()}.md"
    if rule_path.exists():
        typer.echo(rule_path.read_text(encoding="utf-8"))
        return
    typer.echo(f"Documentation not yet available for {rule_code.upper()}.")


@app.command()
def config() -> None:
    """Print the effective configuration as TOML."""
    effective_config = load_config(Path.cwd())
    typer.echo(_format_config_toml(effective_config))


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
    if not paths:
        raise typer.BadParameter("no paths provided; pass a notebook file or directory.")
    notebook_paths: list[Path] = []
    for check_path in paths:
        if not check_path.exists():
            raise typer.BadParameter(
                f"path '{check_path}' does not exist; pass a notebook file or directory."
            )
        if check_path.is_dir():
            discovered_notebooks = tuple(sorted(check_path.rglob("*.ipynb")))
            if not discovered_notebooks:
                typer.echo(f"no notebooks found in directory: {check_path}", err=True)
                raise typer.Exit(code=2)
            notebook_paths.extend(discovered_notebooks)
            continue
        if check_path.suffix != ".ipynb":
            raise typer.BadParameter(
                f"path '{check_path}' is not a .ipynb file; pass a notebook file or directory."
            )
        notebook_paths.append(check_path)
    if not notebook_paths:
        joined_paths = ", ".join(str(path) for path in paths)
        raise typer.BadParameter(f"no notebooks found at: {joined_paths}")
    return tuple(notebook_paths)


def _check_notebook(
    notebook: Notebook,
    config: Config,
    *,
    include_levels: frozenset[Severity],
) -> tuple[Diagnostic, ...]:
    graph = build_dataflow_graph(notebook)
    classified_uses = classify_unresolved_uses(graph)
    include_info = "info" in include_levels
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
    include_levels: frozenset[Severity],
) -> tuple[Diagnostic, ...]:
    return tuple(diagnostic for diagnostic in diagnostics if diagnostic.severity in include_levels)

def _enabled_fixes(fix: str | None, diff: bool) -> frozenset[str]:
    if diff:
        return frozenset({"reorder", "seeds", "clear-counts"})
    if fix is None:
        return frozenset()
    if fix == "all":
        return frozenset({"reorder", "seeds", "clear-counts"})
    return frozenset(fix_id.strip() for fix_id in fix.split(",") if fix_id.strip())

def _parse_include(include: str | None) -> frozenset[Severity]:
    if include is None:
        return _DEFAULT_INCLUDE_LEVELS
    extra_levels: set[Severity] = set()
    for level_token in include.split(","):
        normalized = level_token.strip()
        match normalized:
            case "error" | "warning" | "info":
                extra_levels.add(normalized)
            case _:
                message = f"unknown --include value '{normalized}'; expected error, warning, info."
                typer.echo(message, err=True)
                raise typer.Exit(code=2)
    return _DEFAULT_INCLUDE_LEVELS | extra_levels

def _select_reporter(output_format: str) -> Reporter:
    if output_format == "text":
        return TextReporter()
    if output_format == "json":
        return JsonReporter()
    if output_format == "github":
        return GithubReporter()
    if output_format == "sarif":
        return SarifReporter()
    raise typer.BadParameter(
        f"unknown --output-format value '{output_format}'; "
        "expected one of: text, json, github, sarif."
    )

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

def _format_config_toml(effective_config: Config) -> str:
    libraries_repr = ", ".join(f'"{library}"' for library in effective_config.seeds.libraries)
    return (
        "[tool.nborder]\n"
        "\n"
        "[tool.nborder.seeds]\n"
        f"value = {effective_config.seeds.value}\n"
        f"libraries = [{libraries_repr}]\n"
    )
