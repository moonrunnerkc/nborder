from __future__ import annotations

from nborder.parser.magics import strip_magics


def test_strip_magics_records_line_magics_without_python_source() -> None:
    magic_strip = strip_magics("%load_ext autoreload\nvalue = 1")

    assert magic_strip.stripped_source == "\nvalue = 1"
    assert magic_strip.magics[0].kind == "line"
    assert magic_strip.magics[0].name == "load_ext"


def test_strip_magics_records_shell_assignment_binding() -> None:
    magic_strip = strip_magics("files = !ls *.csv\ncount = len(files)")

    assert magic_strip.stripped_source == "\ncount = len(files)"
    assert magic_strip.magics[0].kind == "shell_assignment"
    assert magic_strip.magics[0].binding == "files"


def test_strip_magics_records_cell_magic_capture_binding() -> None:
    magic_strip = strip_magics("%%capture captured_output\nprint('hello')")

    assert magic_strip.stripped_source == ""
    assert magic_strip.magics[0].kind == "cell"
    assert magic_strip.magics[0].name == "capture"
    assert magic_strip.magics[0].binding == "captured_output"


def test_strip_magics_records_help_syntax() -> None:
    magic_strip = strip_magics("model??")

    assert magic_strip.stripped_source == ""
    assert magic_strip.magics[0].kind == "help"
    assert magic_strip.magics[0].name == "model"


def test_strip_magics_records_auto_call_syntax() -> None:
    magic_strip = strip_magics(",display dataframe")

    assert magic_strip.stripped_source == ""
    assert magic_strip.magics[0].kind == "auto_call"
    assert magic_strip.magics[0].name == ","
