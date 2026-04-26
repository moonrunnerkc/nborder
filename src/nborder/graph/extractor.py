from __future__ import annotations

import libcst as cst
from libcst.metadata import CodePosition, MetadataWrapper, PositionProvider

from nborder.graph.cst_helpers import (
    comp_for_nodes,
    dotted_name,
    from_import_bound_name,
    import_bound_names,
    module_name,
    param_default_values,
    root_name,
    target_names,
)
from nborder.graph.models import CellSymbols, ImportBinding, SymbolDef, SymbolDefKind, SymbolUse
from nborder.graph.wildcards import resolve_wildcard_names
from nborder.parser.models import Cell


def extract_cell_symbols(cell: Cell) -> CellSymbols:
    """Extract cell-scope definitions and uses from one notebook cell.

    Args:
        cell: Parsed notebook cell.

    Returns:
        Symbol records visible to the graph builder.
    """
    definitions = _magic_definitions(cell)
    if cell.kind != "code" or cell.cst_module is None:
        return CellSymbols(cell.index, tuple(definitions), (), (), False)

    wrapper = MetadataWrapper(cell.cst_module, unsafe_skip_copy=True)
    extractor = _CellSymbolVisitor(cell.index)
    wrapper.visit(extractor)
    definitions.extend(extractor.definitions)
    return CellSymbols(
        cell_index=cell.index,
        definitions=tuple(definitions),
        uses=tuple(extractor.uses),
        imports=tuple(extractor.imports),
        has_wildcard_import=extractor.has_wildcard_import,
    )


def _magic_definitions(cell: Cell) -> list[SymbolDef]:
    definitions: list[SymbolDef] = []
    for magic in cell.magics:
        if magic.binding is None:
            continue
        definitions.append(
            SymbolDef(
                name=magic.binding,
                cell_index=cell.index,
                line=magic.line_number,
                column=1,
                kind="magic",
            )
        )
    return definitions


class _CellSymbolVisitor(cst.CSTVisitor):
    METADATA_DEPENDENCIES = (PositionProvider,)

    def __init__(self, cell_index: int) -> None:
        self.cell_index = cell_index
        self.definitions: list[SymbolDef] = []
        self.uses: list[SymbolUse] = []
        self.imports: list[ImportBinding] = []
        self.has_wildcard_import = False
        self._comprehension_locals: list[set[str]] = []

    def visit_Name(self, cst_node: cst.Name) -> None:
        if self._is_comprehension_local(cst_node.value):
            return
        self._add_use(cst_node.value, self._position(cst_node))

    def visit_Attribute(self, cst_node: cst.Attribute) -> bool:
        root_symbol_name = root_name(cst_node)
        if root_symbol_name is not None and not self._is_comprehension_local(root_symbol_name):
            self._add_use(root_symbol_name, self._position(cst_node))
            return False
        return True

    def visit_Assign(self, cst_node: cst.Assign) -> bool:
        for assign_target in cst_node.targets:
            self._record_target_uses(assign_target.target)
            self._record_target_definitions(assign_target.target, "assignment")
        cst_node.value.visit(self)
        return False

    def visit_AnnAssign(self, cst_node: cst.AnnAssign) -> bool:
        self._record_target_uses(cst_node.target)
        self._record_target_definitions(cst_node.target, "assignment")
        cst_node.annotation.visit(self)
        if cst_node.value is not None:
            cst_node.value.visit(self)
        return False

    def visit_AugAssign(self, cst_node: cst.AugAssign) -> bool:
        self._record_expression_use(cst_node.target)
        self._record_target_definitions(cst_node.target, "assignment")
        cst_node.value.visit(self)
        return False

    def visit_FunctionDef(self, cst_node: cst.FunctionDef) -> bool:
        self._add_definition(cst_node.name.value, self._position(cst_node.name), "function")
        for decorator in cst_node.decorators:
            decorator.decorator.visit(self)
        for default_value in param_default_values(cst_node.params):
            default_value.visit(self)
        return_annotation = cst_node.returns
        if return_annotation is not None:
            return_annotation.visit(self)
        return False

    def visit_ClassDef(self, cst_node: cst.ClassDef) -> bool:
        self._add_definition(cst_node.name.value, self._position(cst_node.name), "class")
        for decorator in cst_node.decorators:
            decorator.decorator.visit(self)
        for base_arg in cst_node.bases:
            base_arg.visit(self)
        for keyword_arg in cst_node.keywords:
            keyword_arg.visit(self)
        return False

    def visit_Import(self, cst_node: cst.Import) -> bool:
        for alias_node in cst_node.names:
            bound_names = import_bound_names(alias_node)
            alias_position = self._position(alias_node)
            imported_path = dotted_name(alias_node.name)
            for bound_name in bound_names:
                self._add_definition(bound_name, alias_position, "import")
            self.imports.append(
                ImportBinding(
                    module=imported_path,
                    imported_name=None,
                    bound_name=bound_names[-1] if bound_names else None,
                    cell_index=self.cell_index,
                    line=alias_position.line,
                    column=alias_position.column + 1,
                    kind="import",
                )
            )
        return False

    def visit_ImportFrom(self, cst_node: cst.ImportFrom) -> bool:
        imported_module_name = module_name(cst_node.module)
        import_position = self._position(cst_node)
        if isinstance(cst_node.names, cst.ImportStar):
            self.has_wildcard_import = True
            self.imports.append(
                ImportBinding(
                    imported_module_name,
                    "*",
                    None,
                    self.cell_index,
                    import_position.line,
                    import_position.column + 1,
                    "wildcard",
                )
            )
            for wildcard_name in resolve_wildcard_names(imported_module_name):
                self._add_definition(wildcard_name, import_position, "import")
            return False

        for alias_node in cst_node.names:
            if isinstance(alias_node, cst.ImportAlias):
                bound_name = from_import_bound_name(alias_node)
                alias_position = self._position(alias_node)
                self._add_definition(bound_name, alias_position, "import")
                self.imports.append(
                    ImportBinding(
                        module=imported_module_name,
                        imported_name=dotted_name(alias_node.name),
                        bound_name=bound_name,
                        cell_index=self.cell_index,
                        line=alias_position.line,
                        column=alias_position.column + 1,
                        kind="from",
                    )
                )
        return False

    def visit_For(self, cst_node: cst.For) -> bool:
        self._record_target_definitions(cst_node.target, "assignment")
        cst_node.iter.visit(self)
        cst_node.body.visit(self)
        if cst_node.orelse is not None:
            cst_node.orelse.visit(self)
        return False

    def visit_With(self, cst_node: cst.With) -> bool:
        for with_entry in cst_node.items:
            with_entry.item.visit(self)
            if with_entry.asname is not None:
                self._record_target_definitions(with_entry.asname.name, "assignment")
        cst_node.body.visit(self)
        return False

    def visit_ExceptHandler(self, cst_node: cst.ExceptHandler) -> bool:
        if cst_node.type is not None:
            cst_node.type.visit(self)
        if cst_node.name is not None:
            self._record_target_definitions(cst_node.name.name, "assignment")
        cst_node.body.visit(self)
        return False

    def visit_NamedExpr(self, cst_node: cst.NamedExpr) -> bool:
        self._record_target_definitions(cst_node.target, "walrus")
        cst_node.value.visit(self)
        return False

    def visit_ListComp(self, cst_node: cst.ListComp) -> bool:
        self._visit_comprehension(cst_node.elt, cst_node.for_in)
        return False

    def visit_SetComp(self, cst_node: cst.SetComp) -> bool:
        self._visit_comprehension(cst_node.elt, cst_node.for_in)
        return False

    def visit_GeneratorExp(self, cst_node: cst.GeneratorExp) -> bool:
        self._visit_comprehension(cst_node.elt, cst_node.for_in)
        return False

    def visit_DictComp(self, cst_node: cst.DictComp) -> bool:
        comprehension_nodes = comp_for_nodes(cst_node.for_in)
        local_names = {
            target_name
            for comp_for in comprehension_nodes
            for target_name in target_names(comp_for.target)
        }
        for comp_for in comprehension_nodes:
            comp_for.iter.visit(self)
        self._comprehension_locals.append(local_names)
        cst_node.key.visit(self)
        cst_node.value.visit(self)
        for comp_for in comprehension_nodes:
            for comp_if in comp_for.ifs:
                comp_if.test.visit(self)
        self._comprehension_locals.pop()
        return False

    def _visit_comprehension(self, element_node: cst.BaseExpression, comp_for: cst.CompFor) -> None:
        comprehension_nodes = comp_for_nodes(comp_for)
        local_names = {
            target_name
            for comp_for_node in comprehension_nodes
            for target_name in target_names(comp_for_node.target)
        }
        for comp_for_node in comprehension_nodes:
            comp_for_node.iter.visit(self)
        self._comprehension_locals.append(local_names)
        element_node.visit(self)
        for comp_for_node in comprehension_nodes:
            for comp_if in comp_for_node.ifs:
                comp_if.test.visit(self)
        self._comprehension_locals.pop()

    def _record_target_definitions(
        self,
        target_node: cst.CSTNode,
        kind: SymbolDefKind,
    ) -> None:
        for target_name in target_names(target_node):
            self._add_definition(target_name, self._position(target_node), kind)

    def _record_target_uses(self, target_node: cst.BaseAssignTargetExpression) -> None:
        if isinstance(target_node, cst.Attribute | cst.Subscript):
            self._record_expression_use(target_node)

    def _record_expression_use(self, expression_node: cst.CSTNode) -> None:
        if isinstance(expression_node, cst.Name):
            self._add_use(expression_node.value, self._position(expression_node))
            return
        if isinstance(expression_node, cst.Attribute):
            root_symbol_name = root_name(expression_node)
            if root_symbol_name is not None:
                self._add_use(root_symbol_name, self._position(expression_node))
                return
        expression_node.visit(self)

    def _add_definition(self, name: str, position: CodePosition, kind: SymbolDefKind) -> None:
        self.definitions.append(
            SymbolDef(name, self.cell_index, position.line, position.column + 1, kind)
        )

    def _add_use(self, name: str, position: CodePosition) -> None:
        self.uses.append(SymbolUse(name, self.cell_index, position.line, position.column + 1))

    def _position(self, cst_node: cst.CSTNode) -> CodePosition:
        return self.get_metadata(PositionProvider, cst_node).start

    def _is_comprehension_local(self, name: str) -> bool:
        return any(name in local_names for local_names in self._comprehension_locals)
