from __future__ import annotations

from collections.abc import Iterable

import libcst as cst


def target_names(target_node: cst.CSTNode) -> tuple[str, ...]:
    """Return symbol names assigned by a target node.

    Args:
        target_node: LibCST assignment target node.

    Returns:
        Names bound by the target at notebook cell scope.
    """
    if isinstance(target_node, cst.Name):
        return (target_node.value,)
    if isinstance(target_node, cst.StarredElement):
        return target_names(target_node.value)
    if isinstance(target_node, cst.Tuple | cst.List):
        target_symbol_names: list[str] = []
        for target_element in target_node.elements:
            target_symbol_names.extend(target_names(target_element.value))
        return tuple(target_symbol_names)
    return ()


def comp_for_nodes(comp_for: cst.CompFor) -> tuple[cst.CompFor, ...]:
    """Return chained comprehension for nodes in source order.

    Args:
        comp_for: First comprehension for node.

    Returns:
        The first node followed by nested for nodes.
    """
    comprehension_nodes = [comp_for]
    nested_comp_for = comp_for.inner_for_in
    while nested_comp_for is not None:
        comprehension_nodes.append(nested_comp_for)
        nested_comp_for = nested_comp_for.inner_for_in
    return tuple(comprehension_nodes)


def import_bound_names(alias_node: cst.ImportAlias) -> tuple[str, ...]:
    """Return graph definitions created by an import alias.

    Args:
        alias_node: LibCST import alias node.

    Returns:
        Names made available by the import statement.
    """
    if alias_node.asname is not None:
        return (dotted_name(alias_node.asname.name),)
    import_parts = dotted_name(alias_node.name).split(".")
    return tuple(
        ".".join(import_parts[:part_count]) for part_count in range(1, len(import_parts) + 1)
    )


def from_import_bound_name(alias_node: cst.ImportAlias) -> str:
    """Return the binding created by a from-import alias.

    Args:
        alias_node: LibCST from-import alias node.

    Returns:
        The name bound in cell scope.
    """
    if alias_node.asname is not None:
        return dotted_name(alias_node.asname.name)
    imported_parts = dotted_name(alias_node.name).split(".")
    return imported_parts[0]


def module_name(module_node: cst.BaseExpression | None) -> str:
    """Return a dotted module name for an import-from node.

    Args:
        module_node: LibCST module expression.

    Returns:
        Dotted module path, or an empty string for relative-only imports.
    """
    if module_node is None:
        return ""
    return dotted_name(module_node)


def dotted_name(cst_node: cst.CSTNode) -> str:
    """Return a dotted name from a LibCST name or attribute node.

    Args:
        cst_node: LibCST name-like node.

    Returns:
        Dotted string representation, or an empty string for unsupported nodes.
    """
    if isinstance(cst_node, cst.Name):
        return cst_node.value
    if isinstance(cst_node, cst.Attribute):
        return f"{dotted_name(cst_node.value)}.{cst_node.attr.value}"
    return ""


def root_name(cst_node: cst.CSTNode) -> str | None:
    """Return the root symbol for a name or attribute expression.

    Args:
        cst_node: LibCST expression node.

    Returns:
        Root symbol name if present.
    """
    if isinstance(cst_node, cst.Name):
        return cst_node.value
    if isinstance(cst_node, cst.Attribute):
        return root_name(cst_node.value)
    return None


def param_default_values(params: cst.Parameters) -> Iterable[cst.BaseExpression]:
    """Yield default expressions from a function parameter list.

    Args:
        params: LibCST function parameters.

    Yields:
        Default expressions visible at definition time.
    """
    for param_node in (*params.posonly_params, *params.params, *params.kwonly_params):
        if param_node.default is not None:
            yield param_node.default
