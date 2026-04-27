from __future__ import annotations

import difflib
import sys
from pathlib import Path
from typing import Annotated

import typer

from nborder.check import check_notebook, filter_visible_diagnostics
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
from nborder.rules.types import Diagnostic, Severity

_DEFAULT_INCLUDE_LEVELS: frozenset[Severity] = frozenset({"error", "warning"})
_VALID_FIX_CATEGORIES = frozenset({"reorder", "seeds", "clear-counts"})

_RULE_DOCS_DIR = Path(__file__).parent.parent.parent / "docs" / "rules"

app = typer.Typer(help="Lint Jupyter notebooks for hidden-state and execution-order bugs.")


@app.command()
def check(
    paths: Annotated[
        list[Path],
        typer.Argument(help="Notebook files or directories to check.", exists=True),
    ],
    fix: Annotated[
        bool,
        typer.Option("--fix", help="Apply auto-fixes for fixable diagnostics."),
    ] = False,
    fix_categories: Annotated[
        str | None,
        typer.Option(
            "--fix-categories",
            help="Comma-separated subset: reorder, seeds, clear-counts. Implies --fix.",
        ),
    ] = None,
    output_format: Annotated[
        str,
        typer.Option("--output-format", help="text, json, github, sarif"),
    ] = "text",
    include: Annotated[
        str | None,
        typer.Option(
            "--include",
            help="Comma-separated severity levels to include beyond defaults.",
        ),
    ] = None,
    exit_zero: Annotated[
        bool,
        typer.Option("--exit-zero", help="Always exit 0 even when diagnostics are found."),
    ] = False,
    diff: Annotated[
        bool,
        typer.Option("--diff", help="Print unified diff of fixes without writing."),
    ] = False,
) -> None:
    """Check notebooks for hidden-state and execution-order bugs."""
    notebooks = tuple(_iter_notebook_paths(tuple(paths)))
    include_levels = _parse_include(include)
    enabled_fixes = _enabled_fixes(fix=fix, fix_categories=fix_categories, diff=diff)
    reporter = _select_reporter(output_format)

    diagnostics: list[Diagnostic] = []
    fix_outcomes: list[FixOutcome] = []

    for notebook_path in notebooks:
        try:
            config = load_config(notebook_path)
            notebook = read_notebook(notebook_path)
            notebook_diagnostics = check_notebook(notebook, config, include_levels=include_levels)

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
                    notebook_diagnostics = check_notebook(
                        notebook, config, include_levels=include_levels
                    )

            diagnostics.extend(
                filter_visible_diagnostics(notebook_diagnostics, include_levels=include_levels)
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
    return tuple(notebook_paths)


def _enabled_fixes(*, fix: bool, fix_categories: str | None, diff: bool) -> frozenset[str]:
    if not fix and not fix_categories and not diff:
        return frozenset()
    if fix_categories is None:
        return _VALID_FIX_CATEGORIES
    requested = frozenset(
        category.strip() for category in fix_categories.split(",") if category.strip()
    )
    unknown = requested - _VALID_FIX_CATEGORIES
    if unknown:
        valid_list = ", ".join(sorted(_VALID_FIX_CATEGORIES))
        unknown_list = ", ".join(sorted(unknown))
        typer.echo(
            f"error: unknown --fix-categories value(s): {unknown_list}. Valid: {valid_list}.",
            err=True,
        )
        raise typer.Exit(code=2)
    return requested


def _rewrite_legacy_fix_argument(raw_args: list[str]) -> list[str]:
    """Rewrite deprecated --fix=<value> to --fix-categories=<value> --fix.

    Removed in v0.3.0.
    """
    rewritten: list[str] = []
    saw_legacy_fix = False
    for arg in raw_args:
        if arg.startswith("--fix=") and arg != "--fix=":
            value = arg.removeprefix("--fix=")
            rewritten.extend([f"--fix-categories={value}", "--fix"])
            saw_legacy_fix = True
        else:
            rewritten.append(arg)
    if saw_legacy_fix:
        typer.echo(
            "warning: --fix=<value> is deprecated and will be removed in v0.3.0; "
            "use --fix-categories=<value> instead.",
            err=True,
        )
    return rewritten

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


def main() -> None:
    """Rewrite deprecated arguments, then run the Typer application."""
    sys.argv[1:] = _rewrite_legacy_fix_argument(sys.argv[1:])
    app()


if __name__ == "__main__":
    main()
