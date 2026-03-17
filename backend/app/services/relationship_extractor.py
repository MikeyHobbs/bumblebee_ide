"""Extract relationship edges (CALLS, INHERITS, IMPORTS) from tree-sitter AST."""

from __future__ import annotations

from dataclasses import dataclass, field

import tree_sitter
import tree_sitter_python

from app.services.ast_parser import ParsedNode, _get_parser


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


def _resolve_callee(
    callee_text: str,
    enclosing_func: str,
    scope_map: dict[str, ParsedNode],
    import_map: dict[str, str],
    module_name: str,
) -> str:
    """Resolve a callee name to a qualified function name.

    Resolution order: local scope → class scope → module scope → imported.

    Args:
        callee_text: The raw callee name from the call expression.
        enclosing_func: Qualified name of the enclosing function.
        scope_map: Map of names to ParsedNode instances.
        import_map: Map of imported names to qualified sources.
        module_name: The current module's qualified name.

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
        # Try the last part as the function name
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

    calls: list[RelationshipEdge] = []
    call_order = 0

    def _find_calls(node: tree_sitter.Node, seq: int) -> None:
        nonlocal call_order

        if node.type == "call":
            func_part = node.child_by_field_name("function")
            if func_part is not None:
                callee_text = func_part.text.decode("utf-8")
                resolved = _resolve_callee(callee_text, func_qualified_name, scope_map, import_map, module_name)

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
