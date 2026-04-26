from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

DEFAULT_SEED_LIBRARIES = ("numpy", "torch", "tensorflow", "random", "jax", "sklearn")


@dataclass(frozen=True, slots=True)
class SeedConfig:
    """Configuration for NB103 seed detection and injection."""

    value: int = 42
    libraries: tuple[str, ...] = DEFAULT_SEED_LIBRARIES


@dataclass(frozen=True, slots=True)
class Config:
    """Effective nborder configuration."""

    seeds: SeedConfig = SeedConfig()


def load_config(start_path: Path) -> Config:
    """Load effective configuration for a notebook path.

    Args:
        start_path: Notebook path or directory used to locate pyproject.toml.

    Returns:
        Effective nborder configuration.
    """
    pyproject_path = _find_pyproject(start_path)
    if pyproject_path is None:
        return Config()
    pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    tool_section = _table(pyproject.get("tool"))
    nborder_section = _table(tool_section.get("nborder"))
    seed_section = _table(nborder_section.get("seeds"))
    return Config(seeds=_seed_config(seed_section))


def _find_pyproject(start_path: Path) -> Path | None:
    current_path = start_path if start_path.is_dir() else start_path.parent
    for candidate_root in (current_path, *current_path.parents):
        candidate = candidate_root / "pyproject.toml"
        if candidate.exists():
            return candidate
    return None


def _seed_config(seed_section: dict[str, object]) -> SeedConfig:
    seed_value = seed_section.get("value", 42)
    seed_libraries = seed_section.get("libraries", DEFAULT_SEED_LIBRARIES)
    value = seed_value if isinstance(seed_value, int) else 42
    libraries = _string_tuple(seed_libraries)
    return SeedConfig(value=value, libraries=libraries or DEFAULT_SEED_LIBRARIES)


def _table(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    return {str(key): table_value for key, table_value in value.items()}


def _string_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(str(library) for library in value if isinstance(library, str))