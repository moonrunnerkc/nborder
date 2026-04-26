from __future__ import annotations

import libcst as cst

from nborder.graph.extractor import extract_cell_symbols
from nborder.parser.magics import strip_magics
from nborder.parser.models import Cell


def test_symbol_extractor_records_augmented_assignment_as_use_and_definition() -> None:
    cell = _code_cell(0, "x += 1")

    cell_symbols = extract_cell_symbols(cell)

    assert [symbol_use.name for symbol_use in cell_symbols.uses] == ["x"]
    assert [definition.name for definition in cell_symbols.definitions] == ["x"]


def test_symbol_extractor_records_annotations_and_mutating_targets() -> None:
    cell = _code_cell(0, "config.value: Settings = default\nrows[index] = row")

    cell_symbols = extract_cell_symbols(cell)
    use_names = {symbol_use.name for symbol_use in cell_symbols.uses}

    assert {"config", "Settings", "default", "rows", "index", "row"}.issubset(use_names)


def test_symbol_extractor_records_tuple_and_starred_unpacking_definitions() -> None:
    cell = _code_cell(0, "a, *rest = values")

    cell_symbols = extract_cell_symbols(cell)
    definition_names = {definition.name for definition in cell_symbols.definitions}

    assert definition_names == {"a", "rest"}
    assert [symbol_use.name for symbol_use in cell_symbols.uses] == ["values"]


def test_symbol_extractor_records_loop_context_exception_and_walrus_bindings() -> None:
    cell = _code_cell(
        0,
        "for i in items:\n"
        "    pass\n"
        "with open(path) as reader, context() as manager:\n"
        "    pass\n"
        "try:\n"
        "    pass\n"
        "except Exception as failure:\n"
        "    pass\n"
        "if (count := len(items)) > 0:\n"
        "    pass\n",
    )

    cell_symbols = extract_cell_symbols(cell)
    definition_names = {definition.name for definition in cell_symbols.definitions}

    assert {"i", "reader", "manager", "failure", "count"}.issubset(definition_names)


def test_symbol_extractor_keeps_comprehension_targets_local() -> None:
    cell = _code_cell(0, "[x for x in items if x > threshold]")

    cell_symbols = extract_cell_symbols(cell)
    definition_names = {definition.name for definition in cell_symbols.definitions}
    use_names = {symbol_use.name for symbol_use in cell_symbols.uses}

    assert "x" not in definition_names
    assert "x" not in use_names
    assert use_names == {"items", "threshold"}


def test_symbol_extractor_keeps_nested_function_and_class_locals_private() -> None:
    cell = _code_cell(
        0,
        "def make_value():\n"
        "    hidden_value = 1\n"
        "    return hidden_value\n"
        "class Container:\n"
        "    class_value = make_value()\n",
    )

    cell_symbols = extract_cell_symbols(cell)
    definition_names = {definition.name for definition in cell_symbols.definitions}
    use_names = {symbol_use.name for symbol_use in cell_symbols.uses}

    assert definition_names == {"make_value", "Container"}
    assert "hidden_value" not in use_names
    assert "class_value" not in definition_names


def test_symbol_extractor_records_outer_uses_on_function_and_class_headers() -> None:
    cell = _code_cell(
        0,
        "@decorate(factory)\n"
        "def make_value(limit=default_limit) -> ReturnType:\n"
        "    hidden_value = limit\n"
        "@register\n"
        "class Container(Base, option=setting):\n"
        "    class_value = make_value()\n",
    )

    cell_symbols = extract_cell_symbols(cell)
    use_names = {symbol_use.name for symbol_use in cell_symbols.uses}

    assert {"decorate", "factory", "default_limit", "ReturnType"}.issubset(use_names)
    assert {"register", "Base", "setting"}.issubset(use_names)


def test_symbol_extractor_records_import_bindings_and_wildcard_exports() -> None:
    cell = _code_cell(
        0,
        "import x.y.z\n"
        "import numpy.random as npr\n"
        "from collections import deque\n"
        "from math import *\n",
    )

    cell_symbols = extract_cell_symbols(cell)
    definition_names = {definition.name for definition in cell_symbols.definitions}
    import_modules = {import_binding.module for import_binding in cell_symbols.imports}

    assert {"x", "x.y", "x.y.z", "npr", "deque", "sqrt"}.issubset(definition_names)
    assert cell_symbols.has_wildcard_import is True
    assert {"x.y.z", "numpy.random", "collections", "math"}.issubset(import_modules)


def test_symbol_extractor_records_import_aliases_and_failed_wildcard_lookup() -> None:
    cell = _code_cell(
        0,
        "import package.module as pm\n"
        "from package import module as imported_module\n"
        "from module_that_should_not_exist import *\n",
    )

    cell_symbols = extract_cell_symbols(cell)
    definition_names = {definition.name for definition in cell_symbols.definitions}

    assert {"pm", "imported_module"}.issubset(definition_names)
    assert cell_symbols.has_wildcard_import is True


def test_symbol_extractor_records_relative_import_and_all_exports() -> None:
    cell = _code_cell(0, "from . import local_module\nfrom pathlib import *")

    cell_symbols = extract_cell_symbols(cell)
    definition_names = {definition.name for definition in cell_symbols.definitions}
    import_modules = {import_binding.module for import_binding in cell_symbols.imports}

    assert {"local_module", "Path"}.issubset(definition_names)
    assert "" in import_modules


def test_symbol_extractor_records_for_else_and_optional_handlers() -> None:
    cell = _code_cell(
        0,
        "for row in rows:\n"
        "    pass\n"
        "else:\n"
        "    fallback = default\n"
        "try:\n"
        "    risky()\n"
        "except:\n"
        "    recover()\n",
    )

    cell_symbols = extract_cell_symbols(cell)
    definition_names = {definition.name for definition in cell_symbols.definitions}
    use_names = {symbol_use.name for symbol_use in cell_symbols.uses}

    assert {"row", "fallback"}.issubset(definition_names)
    assert {"rows", "default", "risky", "recover"}.issubset(use_names)


def test_symbol_extractor_handles_all_comprehension_shapes() -> None:
    cell = _code_cell(
        0,
        "{name for name in names}\n"
        "(score for score in scores)\n"
        "{key: value for key, value in pairs if value > minimum}\n"
        "[(left, right) for left in lefts for right in rights if right > left]\n",
    )

    cell_symbols = extract_cell_symbols(cell)
    definition_names = {definition.name for definition in cell_symbols.definitions}
    use_names = {symbol_use.name for symbol_use in cell_symbols.uses}

    assert definition_names == set()
    assert {"names", "scores", "pairs", "minimum", "lefts", "rights"}.issubset(use_names)
    assert not {"name", "score", "key", "value", "left", "right"}.intersection(use_names)


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
