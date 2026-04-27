from __future__ import annotations

from dataclasses import dataclass

from nborder.config import SeedConfig
from nborder.graph.models import DataflowGraph, ImportBinding
from nborder.parser.models import Notebook
from nborder.rules.seed_calls import CallEvent, call_events
from nborder.rules.seed_registry import CallPattern, SeedProbe, enabled_seed_probes
from nborder.rules.types import Diagnostic, FixDescriptor

_PARAMETER_TAGS = frozenset({"parameters", "injected-parameters"})


@dataclass(frozen=True, slots=True)
class LibraryImport:
    """An imported stochastic library binding."""

    probe: SeedProbe
    alias: str
    module: str
    imported_name: str | None


def check_unseeded_stochastic_calls(
    notebook: Notebook,
    graph: DataflowGraph,
    seed_config: SeedConfig,
) -> tuple[Diagnostic, ...]:
    """Emit NB103 diagnostics for stochastic libraries used before seeding.

    Args:
        notebook: Parsed notebook the graph came from.
        graph: Dataflow graph for the notebook.
        seed_config: Effective seed configuration.

    Returns:
        Diagnostics for each library's first unseeded stochastic use.
    """
    probes = enabled_seed_probes(seed_config.libraries)
    active_imports: dict[str, list[LibraryImport]] = {probe.library: [] for probe in probes}
    seeded_kinds: dict[str, set[str]] = {probe.library: set() for probe in probes}
    emitted_libraries: set[str] = set()
    diagnostics: list[Diagnostic] = []
    parameter_names = _parameter_names(notebook, graph)

    for cell in notebook.cells:
        for library_import in _library_imports(graph, cell.index, probes):
            active_imports[library_import.probe.library].append(library_import)

        for call_event in call_events(cell):
            for library_imports in active_imports.values():
                for library_import in library_imports:
                    if _is_seed_call(library_import, call_event, parameter_names):
                        seeded_kinds[library_import.probe.library].add(
                            _seed_kind_for_call(library_import, call_event)
                        )

            for library_name, library_imports in active_imports.items():
                if library_name in emitted_libraries:
                    continue
                stochastic_import = _matching_stochastic_import(library_imports, call_event)
                if stochastic_import is None:
                    continue
                required_kind = _stochastic_required_kind(stochastic_import, call_event)
                if required_kind is None:
                    continue
                if required_kind in seeded_kinds[library_name]:
                    continue
                diagnostics.append(_diagnostic(notebook, graph, stochastic_import, call_event))
                emitted_libraries.add(library_name)
                break

    return tuple(diagnostics)


def _parameter_names(notebook: Notebook, graph: DataflowGraph) -> frozenset[str]:
    parameter_names: set[str] = set()
    for cell in notebook.cells:
        if not cell.tags.intersection(_PARAMETER_TAGS):
            continue
        for definition in graph.symbols_by_cell[cell.index].definitions:
            parameter_names.add(definition.name)
    return frozenset(parameter_names)


def _library_imports(
    graph: DataflowGraph,
    cell_index: int,
    probes: tuple[SeedProbe, ...],
) -> tuple[LibraryImport, ...]:
    imports = graph.symbols_by_cell[cell_index].imports
    library_imports: list[LibraryImport] = []
    for import_binding in imports:
        for probe in probes:
            library_import = _library_import(import_binding, probe)
            if library_import is not None:
                library_imports.append(library_import)
    return tuple(library_imports)


def _library_import(import_binding: ImportBinding, probe: SeedProbe) -> LibraryImport | None:
    if not _module_matches(import_binding.module, probe.import_modules):
        return None
    alias = _alias(import_binding)
    if alias is None:
        return None
    return LibraryImport(probe, alias, import_binding.module, import_binding.imported_name)


def _module_matches(module: str, import_modules: tuple[str, ...]) -> bool:
    return any(
        module == import_module or module.startswith(f"{import_module}.")
        for import_module in import_modules
    )


def _alias(import_binding: ImportBinding) -> str | None:
    if import_binding.bound_name is None:
        return None
    return import_binding.bound_name.split(".", 1)[0]


def _is_seed_call(
    library_import: LibraryImport,
    call_event: CallEvent,
    parameter_names: frozenset[str],
) -> bool:
    if not call_event.arguments:
        return False
    if not any(
        _matches_pattern(library_import, call_event, seed_pattern)
        for seed_pattern in library_import.probe.seed_patterns
    ):
        return False
    return any(_is_seed_argument(argument, parameter_names) for argument in call_event.arguments)


def _is_seed_argument(argument: str, parameter_names: frozenset[str]) -> bool:
    if argument in parameter_names:
        return True
    if argument == "expr":
        return False
    return not argument.isidentifier()


def _matching_stochastic_import(
    library_imports: list[LibraryImport],
    call_event: CallEvent,
) -> LibraryImport | None:
    for library_import in library_imports:
        if any(
            _matches_pattern(library_import, call_event, stochastic_pattern)
            for stochastic_pattern in library_import.probe.stochastic_patterns
        ):
            return library_import
    return None


def _seed_kind_for_call(library_import: LibraryImport, call_event: CallEvent) -> str:
    """Classify a matched seed call by API class.

    For numpy, ``np.random.seed(...)`` seeds the legacy global RandomState used by
    ``np.random.rand`` and friends; ``np.random.default_rng(...)`` only seeds the
    Generator instance it returns. The two kinds are tracked separately so a
    legacy call site is not falsely accepted as seeded by a Generator setup.

    Args:
        library_import: The matched library import for the call.
        call_event: The seed call event under inspection.

    Returns:
        ``"legacy"`` for numpy seed calls, ``"generator"`` for numpy default_rng,
        ``"default"`` for every other library where seed kind is irrelevant.
    """
    if library_import.probe.library != "numpy":
        return "default"
    relative_name = _relative_call_name(library_import, call_event.name)
    if relative_name in {"random.default_rng", "default_rng"}:
        return "generator"
    return "legacy"


def _stochastic_required_kind(
    library_import: LibraryImport,
    call_event: CallEvent,
) -> str | None:
    """Return the seed kind required to consider this stochastic call seeded.

    For numpy, every stochastic call goes through the legacy global RandomState
    and therefore requires ``"legacy"`` seeding. The numpy seed-setup calls
    themselves (``np.random.seed`` and ``np.random.default_rng``) match the
    stochastic prefix pattern but are not real stochastic firings; they return
    ``None`` so the rule does not flag them.

    Args:
        library_import: The matched library import for the stochastic call.
        call_event: The candidate stochastic call event.

    Returns:
        The seed kind that satisfies this call, or ``None`` if the call should
        not fire (e.g., it is itself a seed-setup call).
    """
    relative_name = _relative_call_name(library_import, call_event.name)
    if library_import.probe.library == "numpy":
        if relative_name in {
            "random.seed",
            "random.default_rng",
            "seed",
            "default_rng",
        }:
            return None
        return "legacy"
    return "default"


def _matches_pattern(
    library_import: LibraryImport,
    call_event: CallEvent,
    call_pattern: CallPattern,
) -> bool:
    relative_name = _relative_call_name(library_import, call_event.name)
    if relative_name is None:
        return False
    if call_pattern.kind == "sklearn_random_state":
        return _is_sklearn_random_state_call(library_import, call_event)
    if any(
        _relative_name_excluded(relative_name, excluded)
        for excluded in call_pattern.excluded_suffixes
    ):
        return False
    if _is_numpy_random_binding(library_import) and call_pattern.kind == "attribute_prefix":
        return bool(relative_name) and relative_name not in {"seed", "default_rng"}
    if call_pattern.kind == "attribute_exact":
        return relative_name in call_pattern.suffixes
    return any(
        _relative_name_matches_prefix(relative_name, suffix)
        for suffix in call_pattern.suffixes
    )


def _relative_call_name(library_import: LibraryImport, call_name: str) -> str | None:
    if call_name == library_import.alias:
        return ""
    prefix = f"{library_import.alias}."
    if not call_name.startswith(prefix):
        return None
    return call_name.removeprefix(prefix)


def _is_numpy_random_binding(library_import: LibraryImport) -> bool:
    return library_import.probe.library == "numpy" and (
        library_import.module == "numpy.random" or library_import.imported_name == "random"
    )


def _relative_name_matches_prefix(relative_name: str, suffix: str) -> bool:
    if not suffix:
        return bool(relative_name)
    return (
        relative_name == suffix
        or relative_name.startswith(f"{suffix}.")
        or relative_name.startswith(suffix)
    )


def _relative_name_excluded(relative_name: str, excluded_suffix: str) -> bool:
    return relative_name == excluded_suffix or relative_name.startswith(f"{excluded_suffix}.")


def _is_sklearn_random_state_call(
    library_import: LibraryImport,
    call_event: CallEvent,
) -> bool:
    if not library_import.module.startswith("sklearn"):
        return False
    random_state_value = call_event.keyword_values.get("random_state")
    return random_state_value == "None"


def _diagnostic(
    notebook: Notebook,
    graph: DataflowGraph,
    library_import: LibraryImport,
    call_event: CallEvent,
) -> Diagnostic:
    probe = library_import.probe
    fixable = probe.injection_template is not None
    return Diagnostic(
        code="NB103",
        severity="error",
        message=probe.diagnostic_message,
        notebook_path=notebook.path,
        cell_index=call_event.cell_index,
        cell_id=graph.cells[call_event.cell_index].cell_id,
        line=call_event.line,
        column=call_event.column,
        end_line=call_event.line,
        end_column=call_event.column + len(call_event.name),
        fixable=fixable,
        fix_descriptor=FixDescriptor("seeds", [call_event.cell_index], probe.library)
        if fixable
        else None,
    )