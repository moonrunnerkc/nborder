from __future__ import annotations

import importlib


def resolve_wildcard_names(module_name: str) -> tuple[str, ...]:
    """Resolve names exported by a wildcard import.

    Args:
        module_name: Module referenced by a from-import-star statement.

    Returns:
        Public names exported by the module, or an empty tuple if import fails.
    """
    try:
        imported_module = importlib.import_module(module_name)
    except Exception:
        return ()

    exported_names = getattr(imported_module, "__all__", None)
    if isinstance(exported_names, list | tuple):
        return tuple(
            exported_name for exported_name in exported_names if isinstance(exported_name, str)
        )
    return tuple(name for name in dir(imported_module) if not name.startswith("_"))