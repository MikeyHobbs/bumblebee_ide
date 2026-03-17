"""Extract relationship edges (CALLS, INHERITS, IMPORTS) from tree-sitter AST."""

from __future__ import annotations

from dataclasses import dataclass, field

import tree_sitter
import tree_sitter_python

from app.services.parsing.ast_parser import ParsedNode, _get_parser


@dataclass
class RelationshipEdge:
    """Represents a relationship edge between nodes.

    Attributes:
        edge_type: One of "CALLS", "INHERITS", "IMPORTS".
        source_name: Qualified name of the source node.
        target_name: Qualified name or unresolved name of the target node.
        source_type: Node type of the source.
        target_type: Node type of the target.
        properties: Additional edge properties (call_line, seq, call_order, alias, etc.).
    """

    edge_type: str
    source_name: str
    target_name: str
    source_type: str
    target_type: str
    properties: dict[str, str | int | None] = field(default_factory=dict)


def _build_scope_map(nodes: list[ParsedNode]) -> dict[str, ParsedNode]:
    """Build a lookup map from short names and qualified names to nodes.

    Args:
        nodes: List of parsed structural nodes.

    Returns:
        Dict mapping names to ParsedNode instances.
    """
    scope_map: dict[str, ParsedNode] = {}
    for node in nodes:
        scope_map[node.name] = node
        # Also index by short name for local resolution
        short_name = node.name.rsplit(".", 1)[-1]
        if short_name not in scope_map:
            scope_map[short_name] = node
    return scope_map


def _resolve_relative_import(module_name: str, from_module_text: str) -> str:
    """Resolve a relative import path to an absolute qualified module name.

    Args:
        module_name: The current module's qualified name (e.g. ``app.services.bar``).
        from_module_text: The raw import text including leading dots (e.g. ``.foo``, ``..utils``, ``.``).

    Returns:
        Absolute qualified module name (e.g. ``app.services.foo``).
    """
    # Count leading dots to determine how many levels up
    dots = 0
    for ch in from_module_text:
        if ch == ".":
            dots += 1
        else:
            break
    remainder = from_module_text[dots:]

    # Go up from the current package (parent of module_name)
    parts = module_name.split(".")
    # First dot means "current package" (parent of this module), each extra dot goes one more level up
    levels_up = dots
    if levels_up >= len(parts):
        # Can't go above the root — return what we can
        base = ""
    else:
        base = ".".join(parts[: len(parts) - levels_up])

    if remainder and base:
        return f"{base}.{remainder}"
    elif remainder:
        return remainder
    return base


def _build_import_map(root: tree_sitter.Node, module_name: str) -> dict[str, str]:
    """Build a map of imported names to their source modules.

    Handles both absolute imports (``from app.foo import bar``) and relative
    imports (``from .foo import bar``, ``from ..utils import helper``).  Relative
    imports are resolved against *module_name* so that the resulting qualified
    names match the file-path-based node names stored in the graph.

    Args:
        root: The root tree-sitter node of the module.
        module_name: The qualified module name (e.g. ``app.services.bar``).

    Returns:
        Dict mapping local imported names to their qualified source.
    """
    import_map: dict[str, str] = {}

    for child in root.children:
        if child.type == "import_statement":
            # import foo, import foo.bar
            for name_child in child.named_children:
                if name_child.type == "dotted_name":
                    full_name = name_child.text.decode("utf-8")
                    short_name = full_name.rsplit(".", 1)[-1]
                    import_map[short_name] = full_name
                elif name_child.type == "aliased_import":
                    name_node = name_child.child_by_field_name("name")
                    alias_node = name_child.child_by_field_name("alias")
                    if name_node and alias_node:
                        import_map[alias_node.text.decode("utf-8")] = name_node.text.decode("utf-8")
                    elif name_node:
                        full = name_node.text.decode("utf-8")
                        import_map[full.rsplit(".", 1)[-1]] = full

        elif child.type == "import_from_statement":
            # from foo import bar, from foo.bar import baz as qux
            module_node = child.child_by_field_name("module_name")
            if module_node is None:
                continue
            from_module_raw = module_node.text.decode("utf-8")

            # Resolve relative imports (e.g. ".foo", "..utils", ".")
            if module_node.type == "relative_import":
                from_module = _resolve_relative_import(module_name, from_module_raw)
            else:
                from_module = from_module_raw

            for name_child in child.named_children:
                if name_child == module_node:
                    continue
                if name_child.type == "dotted_name" or name_child.type == "identifier":
                    imported_name = name_child.text.decode("utf-8")
                    import_map[imported_name] = f"{from_module}.{imported_name}"
                elif name_child.type == "aliased_import":
                    name_node = name_child.child_by_field_name("name")
                    alias_node = name_child.child_by_field_name("alias")
                    if name_node:
                        orig = name_node.text.decode("utf-8")
                        alias = alias_node.text.decode("utf-8") if alias_node else orig
                        import_map[alias] = f"{from_module}.{orig}"

    return import_map


def _extract_var_types(
    func_node: tree_sitter.Node,
    import_map: dict[str, str],
) -> dict[str, str]:
    """Extract variable-to-qualified-type mappings from a function.

    Scans function parameters (type annotations) and body (annotated assignments
    and constructor calls) to build a local variable type map used for resolving
    ``obj.method()`` calls cross-file.

    Args:
        func_node: The function_definition tree-sitter node.
        import_map: Map of imported names to qualified sources.

    Returns:
        Dict mapping local variable names to their resolved qualified type names.
    """
    var_types: dict[str, str] = {}

    def _resolve_type(type_text: str) -> str:
        """Resolve a type name through import_map, handling dotted access."""
        if type_text in import_map:
            return import_map[type_text]
        if "." in type_text:
            parts = type_text.split(".", 1)
            if parts[0] in import_map:
                return f"{import_map[parts[0]]}.{parts[1]}"
        return type_text

    # 1. Parameter type annotations: def f(x: TypeName, y: TypeName = default)
    params_node = func_node.child_by_field_name("parameters")
    if params_node:
        for param in params_node.named_children:
            if param.type in ("typed_parameter", "typed_default_parameter"):
                name_child = param.children[0] if param.children else None
                type_child = param.child_by_field_name("type")
                if name_child and type_child and name_child.type == "identifier":
                    var_name = name_child.text.decode("utf-8")
                    if var_name != "self":
                        var_types[var_name] = _resolve_type(type_child.text.decode("utf-8"))

    # 2. Body: var = TypeName(...) and var: TypeName [= ...]
    # tree-sitter Python may wrap assignments in expression_statement or emit them directly
    body = func_node.child_by_field_name("body")
    if body:
        for stmt in body.named_children:
            # Unwrap expression_statement -> assignment (older tree-sitter Python grammar)
            actual = stmt
            if stmt.type == "expression_statement":
                inner = stmt.named_children[0] if stmt.named_children else None
                if inner and inner.type == "assignment":
                    actual = inner

            if actual.type == "assignment":
                lhs = actual.child_by_field_name("left")
                rhs = actual.child_by_field_name("right")
                if lhs and rhs and lhs.type == "identifier":
                    var_name = lhs.text.decode("utf-8")
                    if rhs.type == "call":
                        func_part = rhs.child_by_field_name("function")
                        if func_part:
                            var_types[var_name] = _resolve_type(func_part.text.decode("utf-8"))
            # var: TypeName [= expr]
            elif actual.type == "annotated_assignment":
                lhs = actual.named_children[0] if actual.named_children else None
                type_child = actual.child_by_field_name("annotation")
                if lhs and type_child and lhs.type == "identifier":
                    var_types[lhs.text.decode("utf-8")] = _resolve_type(type_child.text.decode("utf-8"))

    return var_types


def _resolve_callee(
    callee_text: str,
    enclosing_func: str,
    scope_map: dict[str, ParsedNode],
    import_map: dict[str, str],
    module_name: str,
    var_type_map: dict[str, str] | None = None,
) -> str:
    """Resolve a callee name to a qualified function name.

    Resolution order: local scope → class scope → module scope → imported.
    For ``obj.method()`` calls, also consults *var_type_map* (variable-to-type
    mapping built from the enclosing function) and *import_map* to resolve
    cross-file method calls.

    Args:
        callee_text: The raw callee name from the call expression.
        enclosing_func: Qualified name of the enclosing function.
        scope_map: Map of names to ParsedNode instances.
        import_map: Map of imported names to qualified sources.
        module_name: The current module's qualified name.
        var_type_map: Optional variable-to-qualified-type map for the enclosing function.

    Returns:
        Best-effort resolved qualified name.
    """
    # Strip method calls on objects (e.g., self.foo() -> foo, obj.method() -> method)
    base_name = callee_text
    if "." in callee_text:
        parts = callee_text.split(".")
        if parts[0] == "self":
            # self.method() -> resolve to Class.method
            method_name = parts[-1]
            # Find the class containing the enclosing function
            class_prefix = ".".join(enclosing_func.split(".")[:-1])
            candidate = f"{class_prefix}.{method_name}"
            if candidate in scope_map:
                return candidate
        else:
            obj_name = parts[0]
            method_chain = ".".join(parts[1:])

            # Cross-file resolution via variable type map
            if var_type_map and obj_name in var_type_map:
                qualified_type = var_type_map[obj_name]
                return f"{qualified_type}.{method_chain}"

            # Direct import access: import_map["Calculator"] or import_map["calc_mod"]
            if obj_name in import_map:
                return f"{import_map[obj_name]}.{method_chain}"

        # Fall back to last part for local/class/module resolution
        base_name = parts[-1]

    # 1. Local scope: nested function in same enclosing function
    local_candidate = f"{enclosing_func}.{base_name}"
    if local_candidate in scope_map:
        return local_candidate

    # 2. Class scope: sibling method in same class
    parent_parts = enclosing_func.rsplit(".", 1)
    if len(parent_parts) > 1:
        class_candidate = f"{parent_parts[0]}.{base_name}"
        if class_candidate in scope_map:
            return class_candidate

    # 3. Module scope
    module_candidate = f"{module_name}.{base_name}"
    if module_candidate in scope_map:
        return module_candidate

    # 4. Imported name
    if base_name in import_map:
        return import_map[base_name]

    # 5. Full callee_text might be a qualified name
    if callee_text in scope_map:
        return scope_map[callee_text].name

    # Unresolved — return as-is
    return callee_text


def _extract_calls_from_function(
    func_node: tree_sitter.Node,
    func_qualified_name: str,
    scope_map: dict[str, ParsedNode],
    import_map: dict[str, str],
    module_name: str,
) -> list[RelationshipEdge]:
    """Extract CALLS edges from a function body.

    Args:
        func_node: The function_definition tree-sitter node.
        func_qualified_name: Qualified name of the function.
        scope_map: Map of names to ParsedNode instances.
        import_map: Map of imported names to qualified sources.
        module_name: The current module's qualified name.

    Returns:
        List of CALLS relationship edges.
    """
    body = func_node.child_by_field_name("body")
    if body is None:
        return []

    # Build variable→type map for cross-file obj.method() resolution
    var_type_map = _extract_var_types(func_node, import_map)

    calls: list[RelationshipEdge] = []
    call_order = 0

    def _find_calls(node: tree_sitter.Node, seq: int) -> None:
        nonlocal call_order

        if node.type == "call":
            func_part = node.child_by_field_name("function")
            if func_part is not None:
                callee_text = func_part.text.decode("utf-8")
                resolved = _resolve_callee(callee_text, func_qualified_name, scope_map, import_map, module_name, var_type_map)

                calls.append(RelationshipEdge(
                    edge_type="CALLS",
                    source_name=func_qualified_name,
                    target_name=resolved,
                    source_type="Function",
                    target_type="Function",
                    properties={
                        "call_line": node.start_point[0] + 1,
                        "seq": seq,
                        "call_order": call_order,
                    },
                ))
                call_order += 1

        for child in node.children:
            # Don't recurse into nested function/class definitions
            if child.type in ("function_definition", "class_definition", "decorated_definition"):
                continue
            _find_calls(child, seq)

    # Walk body statements to get seq
    for seq, stmt in enumerate(body.named_children):
        _find_calls(stmt, seq)

    return calls


def _extract_inherits(
    class_node: tree_sitter.Node,
    class_qualified_name: str,
    scope_map: dict[str, ParsedNode],
    import_map: dict[str, str],
    module_name: str,
) -> list[RelationshipEdge]:
    """Extract INHERITS edges from a class definition.

    Args:
        class_node: The class_definition tree-sitter node.
        class_qualified_name: Qualified name of the class.
        scope_map: Map of names to ParsedNode instances.
        import_map: Map of imported names to qualified sources.
        module_name: The current module's qualified name.

    Returns:
        List of INHERITS relationship edges.
    """
    edges: list[RelationshipEdge] = []
    superclasses = class_node.child_by_field_name("superclasses")
    if superclasses is None:
        # Also check argument_list for base classes
        for child in class_node.children:
            if child.type == "argument_list":
                superclasses = child
                break

    if superclasses is None:
        return edges

    for child in superclasses.named_children:
        if child.type in ("identifier", "dotted_name", "attribute"):
            base_name = child.text.decode("utf-8")
            # Try to resolve the base class
            resolved = base_name
            if base_name in import_map:
                resolved = import_map[base_name]
            elif f"{module_name}.{base_name}" in scope_map:
                resolved = f"{module_name}.{base_name}"

            edges.append(RelationshipEdge(
                edge_type="INHERITS",
                source_name=class_qualified_name,
                target_name=resolved,
                source_type="Class",
                target_type="Class",
            ))
        elif child.type == "keyword_argument":
            # metaclass=... or other keyword args — skip
            continue

    return edges


def _extract_imports(root: tree_sitter.Node, module_name: str) -> list[RelationshipEdge]:
    """Extract IMPORTS edges from module-level import statements.

    Args:
        root: The root tree-sitter node.
        module_name: The current module's qualified name.

    Returns:
        List of IMPORTS relationship edges.
    """
    edges: list[RelationshipEdge] = []

    for child in root.children:
        if child.type == "import_statement":
            for name_child in child.named_children:
                if name_child.type == "dotted_name":
                    target = name_child.text.decode("utf-8")
                    edges.append(RelationshipEdge(
                        edge_type="IMPORTS",
                        source_name=module_name,
                        target_name=target,
                        source_type="Module",
                        target_type="Module",
                        properties={"alias": None},
                    ))
                elif name_child.type == "aliased_import":
                    name_node = name_child.child_by_field_name("name")
                    alias_node = name_child.child_by_field_name("alias")
                    if name_node:
                        target = name_node.text.decode("utf-8")
                        alias = alias_node.text.decode("utf-8") if alias_node else None
                        edges.append(RelationshipEdge(
                            edge_type="IMPORTS",
                            source_name=module_name,
                            target_name=target,
                            source_type="Module",
                            target_type="Module",
                            properties={"alias": alias},
                        ))

        elif child.type == "import_from_statement":
            module_node = child.child_by_field_name("module_name")
            if module_node is None:
                continue
            target_raw = module_node.text.decode("utf-8")
            # Resolve relative imports to absolute qualified names
            if module_node.type == "relative_import":
                target = _resolve_relative_import(module_name, target_raw)
            else:
                target = target_raw
            edges.append(RelationshipEdge(
                edge_type="IMPORTS",
                source_name=module_name,
                target_name=target,
                source_type="Module",
                target_type="Module",
                properties={"alias": None},
            ))

    return edges


def extract_relationships(
    source: str,
    file_path: str,
    structural_nodes: list[ParsedNode],
    tree: tree_sitter.Tree | None = None,
) -> list[RelationshipEdge]:
    """Extract all relationship edges from a parsed Python file.

    Extracts CALLS, INHERITS, and IMPORTS edges by walking the tree-sitter AST
    and resolving names against the structural node map.

    Args:
        source: The Python source code.
        file_path: The file path (for module name derivation).
        structural_nodes: Previously extracted structural nodes (Module, Class, Function).
        tree: Optional pre-parsed tree-sitter Tree. If None, parses source internally.

    Returns:
        List of all relationship edges found.
    """
    if tree is None:
        parser = _get_parser()
        tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node

    module_name = file_path.replace("/", ".").replace("\\", ".").removesuffix(".py")
    scope_map = _build_scope_map(structural_nodes)
    import_map = _build_import_map(root, module_name)

    all_edges: list[RelationshipEdge] = []

    # Extract IMPORTS
    all_edges.extend(_extract_imports(root, module_name))

    # Walk structural nodes to extract CALLS and INHERITS
    def _walk_for_relationships(ts_node: tree_sitter.Node) -> None:
        for child in ts_node.children:
            actual = child
            if child.type == "decorated_definition":
                for sub in child.children:
                    if sub.type in ("class_definition", "function_definition"):
                        actual = sub
                        break
                else:
                    continue

            if actual.type == "function_definition":
                name_node = actual.child_by_field_name("name")
                if name_node is None:
                    continue
                # Find the qualified name for this function
                func_name = name_node.text.decode("utf-8")
                matching = [n for n in structural_nodes if n.name.endswith(f".{func_name}") and n.node_type == "Function"]
                # Use line number to disambiguate if multiple matches
                func_line = actual.start_point[0] + 1
                for match in matching:
                    if match.start_line == func_line:
                        all_edges.extend(_extract_calls_from_function(
                            actual, match.name, scope_map, import_map, module_name
                        ))
                        break

                # Recurse into nested definitions
                body = actual.child_by_field_name("body")
                if body:
                    _walk_for_relationships(body)

            elif actual.type == "class_definition":
                name_node = actual.child_by_field_name("name")
                if name_node is None:
                    continue
                class_name = name_node.text.decode("utf-8")
                class_line = actual.start_point[0] + 1
                matching = [n for n in structural_nodes if n.name.endswith(f".{class_name}") and n.node_type == "Class"]
                for match in matching:
                    if match.start_line == class_line:
                        all_edges.extend(_extract_inherits(
                            actual, match.name, scope_map, import_map, module_name
                        ))
                        break

                # Recurse into class body
                body = actual.child_by_field_name("body")
                if body:
                    _walk_for_relationships(body)

    _walk_for_relationships(root)

    return all_edges
