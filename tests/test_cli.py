from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

from typer.testing import CliRunner

from nborder.cli import app
from nborder.parser.reader import read_notebook

FIXTURE_ROOT = Path(__file__).parent / "fixtures"


def test_check_reports_nb101_for_non_monotonic_notebook() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "NB101" / "non_monotonic.ipynb"

    command_outcome = runner.invoke(app, ["check", str(notebook_path)])

    assert command_outcome.exit_code == 1
    assert "NB101" in command_outcome.output
    assert "cell_1" in command_outcome.output


def test_check_stays_silent_for_monotonic_notebook() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "NB101" / "monotonic_with_nulls.ipynb"

    command_outcome = runner.invoke(app, ["check", str(notebook_path)])

    assert command_outcome.exit_code == 0
    assert command_outcome.output == ""


def test_check_fix_preserves_clean_notebook_bytes(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture_path = FIXTURE_ROOT / "roundtrip" / "v45_clean.ipynb"
    copied_notebook = tmp_path / fixture_path.name
    shutil.copyfile(fixture_path, copied_notebook)

    command_outcome = runner.invoke(app, ["check", "--fix", str(copied_notebook)])

    assert command_outcome.exit_code == 0
    assert filecmp.cmp(fixture_path, copied_notebook, shallow=False)


def test_check_reports_nb201_and_nb102_from_same_cell() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "phase3" / "mixed.ipynb"

    command_outcome = runner.invoke(app, ["check", str(notebook_path)])

    assert command_outcome.exit_code == 1
    assert "NB201" in command_outcome.output
    assert "NB102" in command_outcome.output


def test_check_hides_wildcard_info_by_default() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "phase3" / "wildcard.ipynb"

    command_outcome = runner.invoke(app, ["check", str(notebook_path)])

    assert command_outcome.exit_code == 0
    assert command_outcome.output == ""


def test_check_can_include_wildcard_info() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "phase3" / "wildcard.ipynb"

    command_outcome = runner.invoke(app, ["check", "--include=info", str(notebook_path)])

    assert command_outcome.exit_code == 1
    assert "Possibly defined by wildcard import from numpy" in command_outcome.output


def test_check_fix_reorder_rewrites_dag_and_clears_counts(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture_path = FIXTURE_ROOT / "phase3" / "reorder_dag.ipynb"
    copied_notebook = tmp_path / fixture_path.name
    shutil.copyfile(fixture_path, copied_notebook)

    command_outcome = runner.invoke(app, ["check", "--fix=reorder", str(copied_notebook)])

    assert command_outcome.exit_code == 0
    assert "reorder: applied" in command_outcome.output
    rewritten_notebook = read_notebook(copied_notebook)
    assert rewritten_notebook.cells[0].cell_id == "define-df"
    assert all(cell.execution_count is None for cell in rewritten_notebook.cells)

    second_outcome = runner.invoke(app, ["check", "--fix=reorder", str(copied_notebook)])

    assert second_outcome.exit_code == 0
    assert "reorder: no-op" in second_outcome.output


def test_check_fix_reorder_bails_on_cycle_but_clear_counts_runs(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture_path = FIXTURE_ROOT / "phase3" / "reorder_cycle.ipynb"
    copied_notebook = tmp_path / fixture_path.name
    shutil.copyfile(fixture_path, copied_notebook)

    command_outcome = runner.invoke(app, ["check", "--fix", str(copied_notebook)])

    assert command_outcome.exit_code == 1
    assert "reorder: bailed" in command_outcome.output
    assert "Cell 1 defines `y` used by cell 0." in command_outcome.output
    assert "clear-counts: applied" in command_outcome.output
    rewritten_notebook = read_notebook(copied_notebook)
    assert [cell.cell_id for cell in rewritten_notebook.cells] == ["cycle-a", "cycle-b"]
    assert all(cell.execution_count is None for cell in rewritten_notebook.cells)


def test_check_output_format_json_emits_parseable_json() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "NB101" / "non_monotonic.ipynb"

    command_outcome = runner.invoke(
        app, ["check", "--output-format=json", str(notebook_path)]
    )

    assert command_outcome.exit_code == 1
    import json as _json

    payload = _json.loads(command_outcome.output)
    assert "diagnostics" in payload
    assert payload["fix_outcomes"] is None
    assert any(diagnostic["code"] == "NB101" for diagnostic in payload["diagnostics"])


def test_check_output_format_github_emits_workflow_command() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "NB101" / "non_monotonic.ipynb"

    command_outcome = runner.invoke(
        app, ["check", "--output-format=github", str(notebook_path)]
    )

    assert command_outcome.exit_code == 1
    assert "::error " in command_outcome.output
    assert "title=NB101" in command_outcome.output


def test_check_output_format_sarif_validates_against_schema() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "NB101" / "non_monotonic.ipynb"

    command_outcome = runner.invoke(
        app, ["check", "--output-format=sarif", str(notebook_path)]
    )

    assert command_outcome.exit_code == 1
    import json as _json

    sarif_log = _json.loads(command_outcome.output)
    assert sarif_log["version"] == "2.1.0"
    assert sarif_log["runs"][0]["tool"]["driver"]["name"] == "nborder"


def test_check_exit_zero_returns_zero_with_diagnostics() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "NB101" / "non_monotonic.ipynb"

    command_outcome = runner.invoke(app, ["check", "--exit-zero", str(notebook_path)])

    assert command_outcome.exit_code == 0
    assert "NB101" in command_outcome.output


def test_rule_command_prints_documentation_when_present(tmp_path: Path) -> None:
    docs_dir = Path(__file__).resolve().parents[1] / "docs" / "rules"
    docs_dir.mkdir(parents=True, exist_ok=True)
    rule_path = docs_dir / "TEST999.md"
    rule_path.write_text("# TEST999 sample rule\n", encoding="utf-8")
    try:
        runner = CliRunner()
        command_outcome = runner.invoke(app, ["rule", "TEST999"])
        assert command_outcome.exit_code == 0
        assert "TEST999 sample rule" in command_outcome.output
    finally:
        rule_path.unlink(missing_ok=True)


def test_rule_command_prints_fallback_when_doc_missing() -> None:
    runner = CliRunner()

    command_outcome = runner.invoke(app, ["rule", "NB999"])

    assert command_outcome.exit_code == 0
    assert "Documentation not yet available for NB999." in command_outcome.output


def test_config_command_prints_effective_toml() -> None:
    runner = CliRunner()

    command_outcome = runner.invoke(app, ["config"])

    assert command_outcome.exit_code == 0
    assert "[tool.nborder.seeds]" in command_outcome.output
    assert "value = 42" in command_outcome.output


def test_check_diff_outputs_json_diff_without_writing(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture_path = FIXTURE_ROOT / "phase3" / "reorder_dag.ipynb"
    copied_notebook = tmp_path / fixture_path.name
    shutil.copyfile(fixture_path, copied_notebook)
    original_bytes = copied_notebook.read_bytes()

    command_outcome = runner.invoke(app, ["check", "--diff", str(copied_notebook)])

    assert command_outcome.exit_code == 1
    assert "Diff for" in command_outcome.output
    assert "---" in command_outcome.output
    assert copied_notebook.read_bytes() == original_bytes
