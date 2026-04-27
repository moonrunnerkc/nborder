from __future__ import annotations

import json
import shutil
from pathlib import Path

from typer.testing import CliRunner

from nborder.cli import app
from nborder.config import SeedConfig
from nborder.fix import seeds as seed_fix
from nborder.fix.pipeline import plan_fix_pipeline
from nborder.graph.builder import build_dataflow_graph
from nborder.graph.models import ImportBinding
from nborder.parser.reader import read_notebook
from nborder.parser.writer import write_notebook
from nborder.rules.nb103 import check_unseeded_stochastic_calls
from nborder.rules.types import Diagnostic

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def _nb103_diagnostics(
    fixture_name: str,
    seed_config: SeedConfig | None = None,
) -> tuple[Diagnostic, ...]:
    notebook = read_notebook(FIXTURE_ROOT / "NB103" / fixture_name)
    graph = build_dataflow_graph(notebook)
    effective_seed_config = seed_config if seed_config is not None else SeedConfig()
    return check_unseeded_stochastic_calls(notebook, graph, effective_seed_config)


def test_numpy_without_seed_fires_nb103() -> None:
    diagnostics = _nb103_diagnostics("numpy_unseeded.ipynb")
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "NB103"
    assert diagnostics[0].fixable is True
    assert diagnostics[0].fix_descriptor is not None
    assert diagnostics[0].fix_descriptor.description == "numpy"


def test_numpy_legacy_seed_counts_as_seeded() -> None:
    diagnostics = _nb103_diagnostics("numpy_legacy_seeded.ipynb")
    assert diagnostics == ()


def test_numpy_generator_only_usage_does_not_fire() -> None:
    diagnostics = _nb103_diagnostics("numpy_modern_seeded.ipynb")
    assert diagnostics == ()


def test_numpy_default_rng_does_not_seed_legacy_random_calls() -> None:
    diagnostics = _nb103_diagnostics("numpy_default_rng_then_legacy.ipynb")
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "NB103"
    assert diagnostics[0].fix_descriptor is not None
    assert diagnostics[0].fix_descriptor.description == "numpy"


def test_torch_cuda_without_seed_fires_nb103() -> None:
    diagnostics = _nb103_diagnostics("torch_cuda_unseeded.ipynb")
    assert len(diagnostics) == 1
    assert diagnostics[0].fix_descriptor is not None
    assert diagnostics[0].fix_descriptor.description == "torch"


def test_numpy_and_torch_fire_one_diagnostic_per_library() -> None:
    diagnostics = _nb103_diagnostics("numpy_torch_unseeded.ipynb")

    libraries = tuple(
        diagnostic.fix_descriptor.description
        for diagnostic in diagnostics
        if diagnostic.fix_descriptor is not None
    )
    assert libraries == ("numpy", "torch")


def test_jax_is_diagnostic_only() -> None:
    diagnostics = _nb103_diagnostics("jax_unseeded.ipynb")
    assert len(diagnostics) == 1
    assert diagnostics[0].fixable is False
    assert "PRNGKey" in diagnostics[0].message


def test_sklearn_random_state_none_is_diagnostic_only() -> None:
    diagnostics = _nb103_diagnostics("sklearn_random_state_none.ipynb")
    assert len(diagnostics) == 1
    assert diagnostics[0].fixable is False
    assert "random_state" in diagnostics[0].message


def test_papermill_parameter_seed_counts_one_level_name_flow(tmp_path: Path) -> None:
    notebook_path = tmp_path / "papermill_seed_parameter.ipynb"
    notebook_path.write_text(
        _parameter_notebook_source(
            parameter_source="seed = 42",
            logic_source=(
                "import numpy as np\n"
                "np.random.seed(seed)\n"
                "values = np.random.rand(3)"
            ),
        ),
        encoding="utf-8",
    )
    notebook = read_notebook(notebook_path)
    graph = build_dataflow_graph(notebook)
    diagnostics = check_unseeded_stochastic_calls(notebook, graph, SeedConfig())
    assert diagnostics == ()


def test_libraries_config_filters_detection() -> None:
    diagnostics = _nb103_diagnostics(
        "config_numpy_only.ipynb",
        SeedConfig(value=42, libraries=("numpy",)),
    )

    assert len(diagnostics) == 1
    assert diagnostics[0].fix_descriptor is not None
    assert diagnostics[0].fix_descriptor.description == "numpy"


def test_real_world_corpus_runs_nb103_without_crashing() -> None:
    for fixture_path in sorted((FIXTURE_ROOT / "real_world").glob("*.ipynb")):
        notebook = read_notebook(fixture_path)
        graph = build_dataflow_graph(notebook)
        check_unseeded_stochastic_calls(notebook, graph, SeedConfig())


def test_seeds_fix_injects_numpy_cell_and_second_pass_is_noop(tmp_path: Path) -> None:
    fixture_path = FIXTURE_ROOT / "NB103" / "numpy_unseeded.ipynb"
    copied_notebook = tmp_path / fixture_path.name
    shutil.copyfile(fixture_path, copied_notebook)
    runner = CliRunner()

    first_outcome = runner.invoke(
        app,
        ["check", "--fix-categories=seeds", str(copied_notebook)],
    )

    assert first_outcome.exit_code == 0
    assert "seeds: applied (numpy seed injected at cell 0)" in first_outcome.output
    rewritten_notebook = read_notebook(copied_notebook)
    assert rewritten_notebook.cells[0].source == (
        "import numpy as np\n"
        "np.random.seed(42)\n"
        "rng = np.random.default_rng(42)\n"
    )

    second_outcome = runner.invoke(
        app,
        ["check", "--fix-categories=seeds", str(copied_notebook)],
    )

    assert second_outcome.exit_code == 0
    assert "seeds: no-op" in second_outcome.output


def test_seeds_fix_uses_user_alias_when_numpy_aliased_elsewhere(tmp_path: Path) -> None:
    copied_notebook = tmp_path / "numpy_custom_alias.ipynb"
    shutil.copyfile(FIXTURE_ROOT / "NB103" / "numpy_custom_alias.ipynb", copied_notebook)

    command_outcome = CliRunner().invoke(
        app,
        ["check", "--fix-categories=seeds", str(copied_notebook)],
    )

    assert command_outcome.exit_code == 0
    rewritten_notebook = read_notebook(copied_notebook)
    assert rewritten_notebook.cells[0].source == (
        "import numpy as numpy_lib\n"
        "numpy_lib.random.seed(42)\n"
        "rng = numpy_lib.random.default_rng(42)\n"
    )


def test_seeds_fix_skips_import_when_parameters_cell_already_imported_library(
    tmp_path: Path,
) -> None:
    copied_notebook = tmp_path / "numpy_preimported_in_parameters.ipynb"
    shutil.copyfile(
        FIXTURE_ROOT / "NB103" / "numpy_preimported_in_parameters.ipynb",
        copied_notebook,
    )

    command_outcome = CliRunner().invoke(
        app,
        ["check", "--fix-categories=seeds", str(copied_notebook)],
    )

    assert command_outcome.exit_code == 0
    assert "seeds: applied (numpy seed injected at cell 1)" in command_outcome.output
    rewritten_notebook = read_notebook(copied_notebook)
    assert rewritten_notebook.cells[1].source == (
        "numpy_lib.random.seed(42)\n"
        "rng = numpy_lib.random.default_rng(42)\n"
    )
    assert len(rewritten_notebook.cells) == 3
    assert rewritten_notebook.cells[0].cell_id == "params-cell"


def test_seeds_fix_injects_torch_cuda_lines(tmp_path: Path) -> None:
    copied_notebook = tmp_path / "torch_cuda_unseeded.ipynb"
    shutil.copyfile(FIXTURE_ROOT / "NB103" / "torch_cuda_unseeded.ipynb", copied_notebook)

    command_outcome = CliRunner().invoke(
        app,
        ["check", "--fix-categories=seeds", str(copied_notebook)],
    )

    assert command_outcome.exit_code == 0
    rewritten_notebook = read_notebook(copied_notebook)
    assert rewritten_notebook.cells[0].source == (
        "import torch\n"
        "torch.manual_seed(42)\n"
        "torch.cuda.manual_seed_all(42)\n"
    )


def test_seeds_fix_injects_one_cell_for_multiple_libraries(tmp_path: Path) -> None:
    copied_notebook = tmp_path / "numpy_torch_unseeded.ipynb"
    shutil.copyfile(FIXTURE_ROOT / "NB103" / "numpy_torch_unseeded.ipynb", copied_notebook)

    command_outcome = CliRunner().invoke(
        app,
        ["check", "--fix-categories=seeds", str(copied_notebook)],
    )

    assert command_outcome.exit_code == 0
    rewritten_notebook = read_notebook(copied_notebook)
    assert len(rewritten_notebook.cells) == 2
    assert rewritten_notebook.cells[0].source == (
        "import numpy as np\n"
        "np.random.seed(42)\n"
        "rng = np.random.default_rng(42)\n"
        "import torch\n"
        "torch.manual_seed(42)\n"
    )


def test_seed_call_lines_cover_stdlib_tensorflow_and_unknown_libraries() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "NB103" / "numpy_unseeded.ipynb")
    graph = build_dataflow_graph(notebook)

    assert seed_fix._seed_call_lines("random", "random", 123, graph) == ("random.seed(123)",)
    assert seed_fix._seed_call_lines("tensorflow", "tf", 123, graph) == (
        "tf.random.set_seed(123)",
    )
    assert seed_fix._seed_call_lines("unknown", "unknown", 123, graph) == ()


def test_seed_alias_resolution_ignores_non_module_import_bindings() -> None:
    from_import = ImportBinding(
        module="numpy",
        imported_name="random",
        bound_name="random",
        cell_index=0,
        line=1,
        column=1,
        kind="from",
    )
    wrong_module = ImportBinding(
        module="pandas",
        imported_name=None,
        bound_name="pd",
        cell_index=0,
        line=1,
        column=1,
        kind="import",
    )
    missing_bound_name = ImportBinding(
        module="numpy",
        imported_name=None,
        bound_name=None,
        cell_index=0,
        line=1,
        column=1,
        kind="import",
    )

    assert seed_fix._alias_for_library(from_import, "numpy") is None
    assert seed_fix._alias_for_library(wrong_module, "numpy") is None
    assert seed_fix._alias_for_library(missing_bound_name, "numpy") is None


def test_jax_seed_fix_is_noop() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "NB103" / "jax_unseeded.ipynb"

    command_outcome = runner.invoke(app, ["check", "--fix-categories=seeds", str(notebook_path)])

    assert command_outcome.exit_code == 1
    assert "seeds: no-op" in command_outcome.output


def test_seed_cell_inserts_after_parameters_cell(tmp_path: Path) -> None:
    copied_notebook = tmp_path / "parameters_insert_position.ipynb"
    copied_notebook.write_text(
        _parameter_notebook_source(
            parameter_source="batch_size = 32",
            logic_source="import numpy as np\nvalues = np.random.rand(3)",
        ),
        encoding="utf-8",
    )

    command_outcome = CliRunner().invoke(
        app,
        ["check", "--fix-categories=seeds", str(copied_notebook)],
    )

    assert command_outcome.exit_code == 0
    rewritten_notebook = read_notebook(copied_notebook)
    assert [cell.cell_id for cell in rewritten_notebook.cells[:2]][0] == "params-insert"
    assert rewritten_notebook.cells[1].source == (
        "import numpy as np\n"
        "np.random.seed(42)\n"
        "rng = np.random.default_rng(42)\n"
    )


def test_config_file_restricts_libraries_for_cli(tmp_path: Path) -> None:
    copied_notebook = tmp_path / "config_numpy_only.ipynb"
    shutil.copyfile(FIXTURE_ROOT / "NB103" / "config_numpy_only.ipynb", copied_notebook)
    (tmp_path / "pyproject.toml").write_text(
        "[tool.nborder.seeds]\nlibraries = [\"numpy\"]\n",
        encoding="utf-8",
    )

    command_outcome = CliRunner().invoke(app, ["check", str(copied_notebook)])

    assert command_outcome.exit_code == 1
    assert command_outcome.output.count("NB103") == 1
    assert "NumPy random API" in command_outcome.output


def test_seeds_apply_when_reorder_bails(tmp_path: Path) -> None:
    copied_notebook = tmp_path / "reorder_cycle_with_seed.ipynb"
    shutil.copyfile(FIXTURE_ROOT / "phase3" / "reorder_cycle.ipynb", copied_notebook)
    notebook_text = copied_notebook.read_text(encoding="utf-8")
    notebook_text = notebook_text.replace(
        '"x = 1\\n"',
        '"import numpy as np\\n",\n    "x = np.random.rand()\\n"',
    )
    copied_notebook.write_text(notebook_text, encoding="utf-8")

    command_outcome = CliRunner().invoke(app, ["check", "--fix", str(copied_notebook)])

    assert command_outcome.exit_code == 1
    assert "reorder: bailed" in command_outcome.output
    assert "seeds: applied" in command_outcome.output
    rewritten_notebook = read_notebook(copied_notebook)
    assert rewritten_notebook.cells[0].source == (
        "import numpy as np\n"
        "np.random.seed(42)\n"
        "rng = np.random.default_rng(42)\n"
    )


def test_seeds_insert_at_new_position_zero_after_reorder_applies() -> None:
    notebook = read_notebook(FIXTURE_ROOT / "NB103" / "reorder_then_seeds.ipynb")
    graph = build_dataflow_graph(notebook)
    diagnostics = (
        *check_unseeded_stochastic_calls(notebook, graph, SeedConfig()),
    )

    cell_order, seed_cell_source, clear_counts, outcomes = plan_fix_pipeline(
        notebook,
        graph,
        diagnostics,
        frozenset({"seeds"}),
    )

    assert cell_order is None
    assert seed_cell_source == (
        "import numpy as np\n"
        "np.random.seed(42)\n"
        "rng = np.random.default_rng(42)\n"
    )
    assert clear_counts is False
    assert outcomes[0].fix_id == "seeds"

    copied_notebook = Path.cwd() / ".pytest_seed_position.ipynb"
    try:
        write_notebook(notebook, copied_notebook, seed_cell_source=seed_cell_source)
        rewritten_notebook = read_notebook(copied_notebook)
        assert rewritten_notebook.cells[0].source == (
            "import numpy as np\n"
            "np.random.seed(42)\n"
            "rng = np.random.default_rng(42)\n"
        )
    finally:
        copied_notebook.unlink(missing_ok=True)


def _parameter_notebook_source(parameter_source: str, logic_source: str) -> str:
    cells = [
        _code_cell(
            "params-insert",
            parameter_source,
            {"language": "python", "tags": ["parameters"]},
        ),
        _code_cell("random-use", logic_source, {"language": "python"}),
    ]
    notebook_json = {
        "cells": cells,
        "metadata": {"language_info": {"name": "python"}},
        "nbformat": 4,
        "nbformat_minor": 5,
    }
    return f"{json.dumps(notebook_json, indent=1)}\n"


def _code_cell(cell_id: str, source: str, metadata: dict[str, object]) -> dict[str, object]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "id": cell_id,
        "metadata": metadata,
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }
