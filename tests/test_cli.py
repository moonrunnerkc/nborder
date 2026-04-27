from __future__ import annotations

import filecmp
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

import nborder.cli as cli_module
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


def test_check_rejects_unknown_include_level() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "phase3" / "wildcard.ipynb"

    command_outcome = runner.invoke(app, ["check", "--include=warn", str(notebook_path)])

    assert command_outcome.exit_code == 2
    assert "unknown --include value 'warn'" in command_outcome.output


def test_check_unknown_flag_exits_with_usage_error() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "roundtrip" / "v45_clean.ipynb"

    command_outcome = runner.invoke(app, ["check", "--fxi", str(notebook_path)])

    assert command_outcome.exit_code == 2
    assert "No such option" in command_outcome.output
    assert "--fxi" in command_outcome.output


def test_check_rejects_non_notebook_file(tmp_path: Path) -> None:
    runner = CliRunner()
    python_file = tmp_path / "notebook.py"
    python_file.write_text("print('not a notebook')\n", encoding="utf-8")

    command_outcome = runner.invoke(app, ["check", str(python_file)])

    assert command_outcome.exit_code == 2
    assert "is not a .ipynb file" in command_outcome.output


def test_check_reports_empty_directory(tmp_path: Path) -> None:
    runner = CliRunner()
    empty_notebook_dir = tmp_path / "empty"
    empty_notebook_dir.mkdir()

    command_outcome = runner.invoke(app, ["check", str(empty_notebook_dir)])

    assert command_outcome.exit_code == 2
    assert "no notebooks found in directory" in command_outcome.output


def test_check_rejects_missing_path(tmp_path: Path) -> None:
    runner = CliRunner()
    missing_notebook = tmp_path / "missing.ipynb"

    command_outcome = runner.invoke(app, ["check", str(missing_notebook)])

    assert command_outcome.exit_code == 2
    assert "does not exist" in command_outcome.output


def test_check_reports_file_removed_after_discovery(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    copied_notebook = tmp_path / "v45_clean.ipynb"
    shutil.copyfile(FIXTURE_ROOT / "roundtrip" / "v45_clean.ipynb", copied_notebook)

    def fail_read(_notebook_path: Path) -> object:
        raise FileNotFoundError(str(copied_notebook))

    monkeypatch.setattr(cli_module, "read_notebook", fail_read)

    command_outcome = runner.invoke(app, ["check", str(copied_notebook)])

    assert command_outcome.exit_code == 2
    assert "file not found" in command_outcome.output


def test_check_reports_unparseable_notebook_without_traceback(tmp_path: Path) -> None:
    runner = CliRunner()
    broken_notebook = tmp_path / "broken.ipynb"
    broken_notebook.write_text(
        '{"cells":[{"cell_type":"code","execution_count":1,"id":"broken",'
        '"metadata":{"language":"python"},"outputs":[],"source":["if True\\n"]}],'
        '"metadata":{"language_info":{"name":"python"}},"nbformat":4,"nbformat_minor":5}\n',
        encoding="utf-8",
    )

    command_outcome = runner.invoke(app, ["check", str(broken_notebook)])

    assert command_outcome.exit_code == 2
    assert "error:" in command_outcome.output
    assert "Failed to parse cell 1" in command_outcome.output
    assert "Traceback" not in command_outcome.output


def test_check_fix_reorder_rewrites_dag_and_clears_counts(tmp_path: Path) -> None:
    runner = CliRunner()
    fixture_path = FIXTURE_ROOT / "phase3" / "reorder_dag.ipynb"
    copied_notebook = tmp_path / fixture_path.name
    shutil.copyfile(fixture_path, copied_notebook)

    command_outcome = runner.invoke(
        app,
        ["check", "--fix-categories=reorder", str(copied_notebook)],
    )

    assert command_outcome.exit_code == 0
    assert "reorder: applied" in command_outcome.output
    rewritten_notebook = read_notebook(copied_notebook)
    assert rewritten_notebook.cells[0].cell_id == "define-df"
    assert all(cell.execution_count is None for cell in rewritten_notebook.cells)

    second_outcome = runner.invoke(
        app,
        ["check", "--fix-categories=reorder", str(copied_notebook)],
    )

    assert second_outcome.exit_code == 0
    assert "reorder: no-op" in second_outcome.output


def test_check_legacy_fix_value_form_emits_deprecation_warning(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    runner = CliRunner()
    fixture_path = FIXTURE_ROOT / "phase3" / "reorder_dag.ipynb"
    copied_notebook = tmp_path / fixture_path.name
    shutil.copyfile(fixture_path, copied_notebook)

    rewritten_args = cli_module._rewrite_legacy_fix_argument(
        ["check", "--fix=reorder", str(copied_notebook)]
    )
    warning_output = capsys.readouterr().err
    command_outcome = runner.invoke(app, rewritten_args)

    assert "deprecated" in warning_output
    assert "--fix-categories=<value>" in warning_output
    assert command_outcome.exit_code == 0
    assert "reorder: applied" in command_outcome.output


def test_check_rejects_unknown_fix_category() -> None:
    runner = CliRunner()
    notebook_path = FIXTURE_ROOT / "roundtrip" / "v45_clean.ipynb"

    command_outcome = runner.invoke(
        app,
        ["check", "--fix-categories=bogus", str(notebook_path)],
    )

    assert command_outcome.exit_code == 2
    assert "unknown --fix-categories value(s): bogus" in command_outcome.output
    assert "clear-counts" in command_outcome.output


def test_rewrite_legacy_fix_argument_leaves_non_legacy_args_silent(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rewritten_args = cli_module._rewrite_legacy_fix_argument(
        ["check", "--fix=", "notebook.ipynb"]
    )

    assert rewritten_args == ["check", "--fix=", "notebook.ipynb"]
    assert capsys.readouterr().err == ""


def test_iter_notebook_paths_rejects_direct_empty_and_missing_inputs(tmp_path: Path) -> None:
    with pytest.raises(Exception, match="no paths provided"):
        cli_module._iter_notebook_paths(())

    with pytest.raises(Exception, match="does not exist"):
        cli_module._iter_notebook_paths((tmp_path / "missing.ipynb",))


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


def test_rule_command_prints_packaged_documentation() -> None:
    runner = CliRunner()

    command_outcome = runner.invoke(app, ["rule", "NB101"])

    assert command_outcome.exit_code == 0
    assert "# NB101: non-monotonic execution counts" in command_outcome.output


def test_rule_command_prints_fallback_when_doc_missing() -> None:
    runner = CliRunner()

    command_outcome = runner.invoke(app, ["rule", "NB999"])

    assert command_outcome.exit_code == 0
    assert "Documentation not yet available for NB999." in command_outcome.output


def test_select_reporter_rejects_unknown_output_format() -> None:
    with pytest.raises(Exception, match="unknown --output-format value 'xml'"):
        cli_module._select_reporter("xml")


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
