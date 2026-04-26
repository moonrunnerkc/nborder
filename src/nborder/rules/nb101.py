from __future__ import annotations

from nborder.parser.models import Notebook
from nborder.rules.types import Diagnostic, FixDescriptor


def check_non_monotonic_execution_counts(notebook: Notebook) -> tuple[Diagnostic, ...]:
    """Detect execution counts that decrease in source order.

    Args:
        notebook: Parsed notebook to inspect.

    Returns:
        Diagnostics for code cells whose execution count is lower than a previous count.
    """
    diagnostics: list[Diagnostic] = []
    previous_count: int | None = None
    for cell in notebook.cells:
        current_count = cell.execution_count
        if current_count is None:
            continue
        if previous_count is not None and current_count <= previous_count:
            diagnostics.append(
                Diagnostic(
                    code="NB101",
                    severity="error",
                    message=(
                        f"Execution count {current_count} appears after {previous_count}. "
                        "The notebook was not run in source order."
                    ),
                    notebook_path=notebook.path,
                    cell_index=cell.index,
                    cell_id=cell.cell_id,
                    line=1,
                    column=1,
                    end_line=1,
                    end_column=1,
                    fixable=True,
                    fix_descriptor=FixDescriptor(
                        fix_id="clear-counts",
                        target_cells=[cell.index],
                        description="Clear execution counts for notebook cells",
                    ),
                )
            )
        previous_count = current_count
    return tuple(diagnostics)
