from __future__ import annotations

import math
import pathlib

_STATIC_WILDCARD_EXPORTS: dict[str, tuple[str, ...]] = {
    "math": tuple(name for name in dir(math) if not name.startswith("_")),
    "pathlib": tuple(name for name in dir(pathlib) if not name.startswith("_")),
}


def resolve_wildcard_names(module_name: str) -> tuple[str, ...]:
    """Resolve names exported by a wildcard import.

    Args:
        module_name: Module referenced by a from-import-star statement.

    Returns:
        Public names from a static export map, or an empty tuple for unknown modules.
    """
    return _STATIC_WILDCARD_EXPORTS.get(module_name, ())