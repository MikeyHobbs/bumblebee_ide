"""Extract Variable nodes and ASSIGNS, MUTATES, READS, RETURNS edges."""

from __future__ import annotations

from dataclasses import dataclass, field

import tree_sitter

from app.services.parsing.ast_parser import ParsedNode, _get_parser
from app.services.parsing.statement_extractor import StatementNode

# Methods that mutate their receiver (configurable allowlist)
MUTATION_METHODS: set[str] = {
    "append", "extend", "insert", "remove", "pop", "clear", "sort", "reverse",  # list
    "update", "setdefault", "popitem",  # dict
    "add", "discard", "difference_update", "intersection_update", "symmetric_difference_update",  # set
    "write", "writelines", "truncate",  # file-like
    "acquire", "release",  # lock-like
}


@dataclass
class VariableNode:
    """Represents a Variable node in the graph.

    Attributes:
        name: Qualified variable name (e.g., "module.func.var_name").
        scope: Full scope path (e.g., "module.Class.method.var_name").
        origin_line: Line where the variable is first assigned.
        origin_func: Qualified name of the function where first assigned.
        type_hint: Type annotation if present.
        module_path: File path for re-indexing.
    """

    name: str
    scope: str
    origin_line: int
    origin_func: str
    type_hint: str | None = None
    module_path: str = ""


@dataclass
class VariableEdge:
    """Represents a variable interaction edge.

    Attributes:
        edge_type: One of "ASSIGNS", "MUTATES", "READS", "RETURNS".
        source_name: Name of the source (usually a Function).
        target_name: Name of the target (usually a Variable).
        source_type: Node type of source.
        target_type: Node type of target.
        properties: Additional edge properties.
    """

    edge_type: str
    source_name: str
    target_name: str
    source_type: str
    target_type: str
    properties: dict[str, str | int | bool | None] = field(default_factory=dict)


@dataclass
class VariableResult:
    """Result of variable extraction.

    Attributes:
        nodes: Variable nodes.
        edges: ASSIGNS, MUTATES, READS, RETURNS edges.
    """

    nodes: list[VariableNode]
    edges: list[VariableEdge]


def _get_control_context(
    stmt_node: tree_sitter.Node,
) -> tuple[str | None, str | None]:
    """Walk up from a statement to find if it's inside a control flow branch.

    Args:
        stmt_node: The tree-sitter node of the statement.

    Returns:
        Tuple of (control_context, branch) or (None, None).
    """
    node = stmt_node.parent
    while node is not None:
        if node.type == "if_clause" or (node.type == "block" and node.parent and node.parent.type == "if_statement"):
            parent = node.parent
            if parent and parent.type == "if_statement":
                cond = parent.child_by_field_name("condition")
                if cond:
                    return (cond.text.decode("utf-8"), "if")
        elif node.type == "elif_clause":
            cond = node.child_by_field_name("condition")
            if cond:
                return (cond.text.decode("utf-8"), "elif")
        elif node.type == "else_clause":
            # Walk up to find the parent if/for/while
            parent = node.parent
            if parent:
                cond = parent.child_by_field_name("condition")
                if cond:
                    return (cond.text.decode("utf-8"), "else")
            return (None, "else")
        elif node.type == "for_statement":
            left = node.child_by_field_name("left")
            right = node.child_by_field_name("right")
            if left and right:
                return (f"{left.text.decode('utf-8')} in {right.text.decode('utf-8')}", "for")
        elif node.type == "while_statement":
            cond = node.child_by_field_name("condition")
            if cond:
                return (cond.text.decode("utf-8"), "while")
        elif node.type == "except_clause":
            for child in node.children:
                if child.type not in ("except", ":", "block", "as", "identifier"):
                    return (child.text.decode("utf-8"), "except")
            return (None, "except")
        elif node.type in ("function_definition", "class_definition", "module"):
            break
        node = node.parent
    return (None, None)


def _extract_type_hint(node: tree_sitter.Node) -> str | None:
    """Extract type annotation from an assignment if present."""
    if node.type == "type" or node.type == "annotation":
        return node.text.decode("utf-8")
    # For typed assignments: x: int = 5
    type_node = node.child_by_field_name("type")
    if type_node:
        return type_node.text.decode("utf-8")
    return None


def _get_assignment_targets(node: tree_sitter.Node) -> list[str]:
    """Extract all assignment target names from an assignment node.

    Handles simple assignment, augmented assignment, tuple unpacking, etc.

    Args:
        node: The assignment tree-sitter node.

    Returns:
        List of variable name strings.
    """
    targets: list[str] = []

    if node.type == "assignment":
        left = node.child_by_field_name("left")
        if left:
            _collect_names(left, targets)
    elif node.type == "augmented_assignment":
        left = node.child_by_field_name("left")
        if left:
            _collect_names(left, targets)
    elif node.type == "named_expression":
        # walrus operator :=
        name_node = node.child_by_field_name("name")
        if name_node:
            targets.append(name_node.text.decode("utf-8"))

    return targets


def _collect_names(node: tree_sitter.Node, targets: list[str]) -> None:
    """Recursively collect identifier names from an expression (handles unpacking)."""
    if node.type == "identifier":
        targets.append(node.text.decode("utf-8"))
    elif node.type == "attribute":
        # self.x or obj.attr
        targets.append(node.text.decode("utf-8"))
    elif node.type in ("pattern_list", "tuple_pattern", "list_pattern", "tuple", "list"):
        for child in node.named_children:
            _collect_names(child, targets)
    elif node.type == "subscript":
        # x[key] = ... — this is a mutation, not an assignment to a new variable
        obj = node.child_by_field_name("value")
        if obj:
            targets.append(obj.text.decode("utf-8"))


def _is_self_attribute(name: str) -> bool:
    """Check if a name is a self.x attribute access."""
    return name.startswith("self.")


def _make_variable_name(raw_name: str, func_name: str, class_name: str | None) -> str:
    """Create a qualified variable name.

    Args:
        raw_name: The raw variable name from source.
        func_name: Qualified name of the enclosing function.
        class_name: Qualified name of the enclosing class, if any.

    Returns:
        Qualified variable name.
    """
    if _is_self_attribute(raw_name):
        attr = raw_name.replace("self.", "")
        if class_name:
            return f"{class_name}.{attr}"
        return f"{func_name}.{raw_name}"
    return f"{func_name}.{raw_name}"


def _find_enclosing_class(func_name: str, structural_nodes: list[ParsedNode]) -> str | None:
    """Find the class that contains a method."""
    parts = func_name.rsplit(".", 1)
    if len(parts) < 2:
        return None
    parent_name = parts[0]
    for node in structural_nodes:
        if node.name == parent_name and node.node_type == "Class":
            return parent_name
    return None


def _extract_from_function(
    func_ts_node: tree_sitter.Node,
    func_name: str,
    class_name: str | None,
    module_path: str,
    variables: dict[str, VariableNode],
    edges: list[VariableEdge],
    stmt_nodes: list[StatementNode],
) -> None:
    """Extract variable interactions from a single function body.

    Args:
        func_ts_node: The function_definition tree-sitter node.
        func_name: Qualified function name.
        class_name: Qualified class name if this is a method.
        module_path: File path.
        variables: Accumulator dict of variable name -> VariableNode.
        edges: Accumulator for edges.
        stmt_nodes: Statement nodes for PART_OF linking.
    """
    body = func_ts_node.child_by_field_name("body")
    if body is None:
        return

    # Track parameters as variables
    params = func_ts_node.child_by_field_name("parameters")
    if params:
        for param in params.named_children:
            param_name = None
            type_hint = None
            if param.type == "identifier":
                param_name = param.text.decode("utf-8")
            elif param.type in ("default_parameter", "typed_parameter", "typed_default_parameter"):
                name_node = param.child_by_field_name("name") or (
                    param.named_children[0] if param.named_children else None
                )
                if name_node:
                    param_name = name_node.text.decode("utf-8")
                type_node = param.child_by_field_name("type")
                if type_node:
                    type_hint = type_node.text.decode("utf-8")
            elif param.type == "list_splat_pattern" and param.named_children:
                param_name = "*" + param.named_children[0].text.decode("utf-8")
            elif param.type == "dictionary_splat_pattern" and param.named_children:
                param_name = "**" + param.named_children[0].text.decode("utf-8")

            if param_name and param_name != "self" and param_name != "cls":
                var_name = f"{func_name}.{param_name}"
                if var_name not in variables:
                    variables[var_name] = VariableNode(
                        name=var_name,
                        scope=func_name,
                        origin_line=param.start_point[0] + 1,
                        origin_func=func_name,
                        type_hint=type_hint,
                        module_path=module_path,
                    )

    # Track for-loop variables
    _extract_for_vars(body, func_name, class_name, module_path, variables, edges)

    # Walk body for assignments, mutations, reads, returns
    seq = 0
    _walk_body_for_vars(body, func_name, class_name, module_path, variables, edges, stmt_nodes, seq)


def _extract_for_vars(
    body: tree_sitter.Node,
    func_name: str,
    class_name: str | None,
    module_path: str,
    variables: dict[str, VariableNode],
    edges: list[VariableEdge],
) -> None:
    """Extract for-loop iteration variables."""
    for child in body.children:
        if child.type == "for_statement":
            left = child.child_by_field_name("left")
            if left:
                targets: list[str] = []
                _collect_names(left, targets)
                for raw_name in targets:
                    var_name = _make_variable_name(raw_name, func_name, class_name)
                    cc, branch = _get_control_context(child)
                    if var_name not in variables:
                        variables[var_name] = VariableNode(
                            name=var_name,
                            scope=func_name,
                            origin_line=child.start_point[0] + 1,
                            origin_func=func_name,
                            module_path=module_path,
                        )
                    edges.append(VariableEdge(
                        edge_type="ASSIGNS",
                        source_name=func_name,
                        target_name=var_name,
                        source_type="Function",
                        target_type="Variable",
                        properties={
                            "line": child.start_point[0] + 1,
                            "col": left.start_point[1],
                            "seq": child.start_point[0],
                            "is_rebind": False,
                            "control_context": cc,
                            "branch": branch,
                        },
                    ))
            # Recurse into for body
            for_body = child.child_by_field_name("body")
            if for_body:
                _extract_for_vars(for_body, func_name, class_name, module_path, variables, edges)

        elif child.type in ("if_statement", "while_statement", "with_statement", "try_statement"):
            for sub in child.children:
                if sub.type == "block":
                    _extract_for_vars(sub, func_name, class_name, module_path, variables, edges)
                elif sub.type in ("elif_clause", "else_clause", "except_clause", "finally_clause"):
                    for subsub in sub.children:
                        if subsub.type == "block":
                            _extract_for_vars(subsub, func_name, class_name, module_path, variables, edges)


def _walk_body_for_vars(
    body: tree_sitter.Node,
    func_name: str,
    class_name: str | None,
    module_path: str,
    variables: dict[str, VariableNode],
    edges: list[VariableEdge],
    stmt_nodes: list[StatementNode],
    seq: int,
) -> int:
    """Walk a function body recursively to extract all variable interactions.

    Returns the updated seq counter.
    """
    for child in body.named_children:
        if child.type in ("function_definition", "class_definition", "decorated_definition"):
            continue

        cc, branch = _get_control_context(child)

        if child.type == "expression_statement":
            inner = child.named_children[0] if child.named_children else None
            if inner and inner.type in ("assignment", "augmented_assignment"):
                _handle_assignment(inner, func_name, class_name, module_path, variables, edges, seq, cc, branch)
            elif inner and inner.type == "named_expression":
                _handle_assignment(inner, func_name, class_name, module_path, variables, edges, seq, cc, branch)
            else:
                # Expression statement — check for mutations and reads
                if inner:
                    _extract_mutations_and_reads(inner, func_name, class_name, module_path, variables, edges, seq, cc, branch)
            seq += 1

        elif child.type in ("assignment", "augmented_assignment"):
            _handle_assignment(child, func_name, class_name, module_path, variables, edges, seq, cc, branch)
            seq += 1

        elif child.type == "return_statement":
            _handle_return(child, func_name, class_name, module_path, variables, edges, seq, cc, branch)
            seq += 1

        elif child.type in ("if_statement", "for_statement", "while_statement", "try_statement", "with_statement"):
            # Extract reads from conditions
            cond = child.child_by_field_name("condition")
            if cond:
                _extract_reads_from_expr(cond, func_name, class_name, module_path, variables, edges, seq, cc, branch)
            # Recurse into control flow bodies
            for sub in child.children:
                if sub.type == "block":
                    seq = _walk_body_for_vars(
                        sub, func_name, class_name, module_path, variables, edges, stmt_nodes, seq
                    )
                elif sub.type in ("elif_clause", "else_clause", "except_clause", "finally_clause"):
                    # Extract reads from elif conditions
                    elif_cond = sub.child_by_field_name("condition")
                    if elif_cond:
                        _extract_reads_from_expr(
                            elif_cond, func_name, class_name, module_path, variables, edges, seq, cc, branch
                        )
                    for subsub in sub.children:
                        if subsub.type == "block":
                            seq = _walk_body_for_vars(
                                subsub, func_name, class_name, module_path, variables, edges, stmt_nodes, seq
                            )

        else:
            seq += 1

    return seq


def _handle_assignment(
    node: tree_sitter.Node,
    func_name: str,
    class_name: str | None,
    module_path: str,
    variables: dict[str, VariableNode],
    edges: list[VariableEdge],
    seq: int,
    cc: str | None,
    branch: str | None,
) -> None:
    """Handle an assignment statement, creating Variable nodes and ASSIGNS edges."""
    targets = _get_assignment_targets(node)
    type_hint = _extract_type_hint(node)

    # Also extract reads from the RHS
    rhs = node.child_by_field_name("right") or node.child_by_field_name("value")
    if rhs:
        _extract_reads_from_expr(rhs, func_name, class_name, module_path, variables, edges, seq, cc, branch)

    for raw_name in targets:
        # Subscript assignment is a mutation, not a new variable assignment
        if "[" in raw_name:
            continue

        var_name = _make_variable_name(raw_name, func_name, class_name)
        is_rebind = var_name in variables

        if not is_rebind:
            variables[var_name] = VariableNode(
                name=var_name,
                scope=func_name,
                origin_line=node.start_point[0] + 1,
                origin_func=func_name,
                type_hint=type_hint,
                module_path=module_path,
            )

        edges.append(VariableEdge(
            edge_type="ASSIGNS",
            source_name=func_name,
            target_name=var_name,
            source_type="Function",
            target_type="Variable",
            properties={
                "line": node.start_point[0] + 1,
                "col": node.start_point[1],
                "seq": seq,
                "is_rebind": is_rebind,
                "control_context": cc,
                "branch": branch,
            },
        ))

    # Handle subscript assignment as mutation
    if node.type == "assignment":
        left = node.child_by_field_name("left")
        if left and left.type == "subscript":
            obj = left.child_by_field_name("value")
            if obj:
                raw = obj.text.decode("utf-8")
                var_name = _make_variable_name(raw, func_name, class_name)
                edges.append(VariableEdge(
                    edge_type="MUTATES",
                    source_name=func_name,
                    target_name=var_name,
                    source_type="Function",
                    target_type="Variable",
                    properties={
                        "line": node.start_point[0] + 1,
                        "seq": seq,
                        "mutation_kind": "subscript_assign",
                        "control_context": cc,
                        "branch": branch,
                    },
                ))

    # Handle attribute assignment (obj.attr = ...) as mutation if obj is known
    if node.type == "assignment":
        left = node.child_by_field_name("left")
        if left and left.type == "attribute":
            obj_text = left.text.decode("utf-8")
            if _is_self_attribute(obj_text):
                # Already handled as an assignment to self.x
                pass
            else:
                # obj.attr = ... is an attr_assign mutation on obj
                obj = left.child_by_field_name("object")
                if obj:
                    raw = obj.text.decode("utf-8")
                    var_name = _make_variable_name(raw, func_name, class_name)
                    if var_name in variables:
                        edges.append(VariableEdge(
                            edge_type="MUTATES",
                            source_name=func_name,
                            target_name=var_name,
                            source_type="Function",
                            target_type="Variable",
                            properties={
                                "line": node.start_point[0] + 1,
                                "seq": seq,
                                "mutation_kind": "attr_assign",
                                "control_context": cc,
                                "branch": branch,
                            },
                        ))


def _extract_mutations_and_reads(
    node: tree_sitter.Node,
    func_name: str,
    class_name: str | None,
    module_path: str,
    variables: dict[str, VariableNode],
    edges: list[VariableEdge],
    seq: int,
    cc: str | None,
    branch: str | None,
) -> None:
    """Extract mutation method calls and reads from an expression."""
    if node.type == "call":
        func_part = node.child_by_field_name("function")
        if func_part and func_part.type == "attribute":
            obj = func_part.child_by_field_name("object")
            attr = func_part.child_by_field_name("attribute")
            if obj and attr:
                method_name = attr.text.decode("utf-8")
                if method_name in MUTATION_METHODS:
                    raw = obj.text.decode("utf-8")
                    var_name = _make_variable_name(raw, func_name, class_name)
                    edges.append(VariableEdge(
                        edge_type="MUTATES",
                        source_name=func_name,
                        target_name=var_name,
                        source_type="Function",
                        target_type="Variable",
                        properties={
                            "line": node.start_point[0] + 1,
                            "seq": seq,
                            "mutation_kind": "method_call",
                            "control_context": cc,
                            "branch": branch,
                        },
                    ))
                    # Also extract reads from the arguments
                    args = node.child_by_field_name("arguments")
                    if args:
                        _extract_reads_from_expr(args, func_name, class_name, module_path, variables, edges, seq, cc, branch)
                    return

    # General read extraction
    _extract_reads_from_expr(node, func_name, class_name, module_path, variables, edges, seq, cc, branch)


def _extract_reads_from_expr(
    node: tree_sitter.Node,
    func_name: str,
    class_name: str | None,
    module_path: str,
    variables: dict[str, VariableNode],
    edges: list[VariableEdge],
    seq: int,
    cc: str | None,
    branch: str | None,
) -> None:
    """Extract READS edges for variables referenced in an expression."""
    seen: set[str] = set()
    _collect_reads(node, func_name, class_name, variables, edges, seq, cc, branch, seen)


def _collect_reads(
    node: tree_sitter.Node,
    func_name: str,
    class_name: str | None,
    variables: dict[str, VariableNode],
    edges: list[VariableEdge],
    seq: int,
    cc: str | None,
    branch: str | None,
    seen: set[str],
) -> None:
    """Recursively collect READS edges from an expression tree."""
    if node.type == "identifier":
        raw = node.text.decode("utf-8")
        if raw in ("self", "cls", "True", "False", "None"):
            return
        var_name = _make_variable_name(raw, func_name, class_name)
        if var_name in variables and var_name not in seen:
            seen.add(var_name)
            edges.append(VariableEdge(
                edge_type="READS",
                source_name=func_name,
                target_name=var_name,
                source_type="Function",
                target_type="Variable",
                properties={
                    "line": node.start_point[0] + 1,
                    "seq": seq,
                    "control_context": cc,
                    "branch": branch,
                },
            ))
    elif node.type == "attribute" and node.child_by_field_name("object"):
        obj = node.child_by_field_name("object")
        if obj and obj.type == "identifier" and obj.text.decode("utf-8") == "self":
            attr = node.child_by_field_name("attribute")
            if attr:
                raw = f"self.{attr.text.decode('utf-8')}"
                var_name = _make_variable_name(raw, func_name, class_name)
                if var_name in variables and var_name not in seen:
                    seen.add(var_name)
                    edges.append(VariableEdge(
                        edge_type="READS",
                        source_name=func_name,
                        target_name=var_name,
                        source_type="Function",
                        target_type="Variable",
                        properties={
                            "line": node.start_point[0] + 1,
                            "seq": seq,
                            "control_context": cc,
                            "branch": branch,
                        },
                    ))
            return  # Don't recurse into self.attr children

    for child in node.children:
        if child.type in ("function_definition", "class_definition", "lambda"):
            continue
        _collect_reads(child, func_name, class_name, variables, edges, seq, cc, branch, seen)


def _handle_return(
    node: tree_sitter.Node,
    func_name: str,
    class_name: str | None,
    module_path: str,
    variables: dict[str, VariableNode],
    edges: list[VariableEdge],
    seq: int,
    cc: str | None,
    branch: str | None,
) -> None:
    """Handle return/yield statements, creating RETURNS edges."""
    # Extract the return value expression
    for child in node.named_children:
        _extract_return_vars(child, func_name, class_name, variables, edges, seq, cc, branch)


def _extract_return_vars(
    node: tree_sitter.Node,
    func_name: str,
    class_name: str | None,
    variables: dict[str, VariableNode],
    edges: list[VariableEdge],
    seq: int,
    cc: str | None,
    branch: str | None,
) -> None:
    """Extract RETURNS edges from a return value expression."""
    if node.type == "identifier":
        raw = node.text.decode("utf-8")
        if raw in ("self", "cls", "True", "False", "None"):
            return
        var_name = _make_variable_name(raw, func_name, class_name)
        if var_name in variables:
            edges.append(VariableEdge(
                edge_type="RETURNS",
                source_name=func_name,
                target_name=var_name,
                source_type="Function",
                target_type="Variable",
                properties={
                    "line": node.start_point[0] + 1,
                    "seq": seq,
                    "control_context": cc,
                    "branch": branch,
                },
            ))
    elif node.type == "attribute" and node.child_by_field_name("object"):
        obj = node.child_by_field_name("object")
        if obj and obj.type == "identifier" and obj.text.decode("utf-8") == "self":
            attr = node.child_by_field_name("attribute")
            if attr:
                raw = f"self.{attr.text.decode('utf-8')}"
                var_name = _make_variable_name(raw, func_name, class_name)
                if var_name in variables:
                    edges.append(VariableEdge(
                        edge_type="RETURNS",
                        source_name=func_name,
                        target_name=var_name,
                        source_type="Function",
                        target_type="Variable",
                        properties={
                            "line": node.start_point[0] + 1,
                            "seq": seq,
                            "control_context": cc,
                            "branch": branch,
                        },
                    ))

    for child in node.children:
        _extract_return_vars(child, func_name, class_name, variables, edges, seq, cc, branch)


def extract_variables(
    source: str,
    file_path: str,
    structural_nodes: list[ParsedNode],
    stmt_nodes: list[StatementNode] | None = None,
    tree: tree_sitter.Tree | None = None,
) -> VariableResult:
    """Extract all Variable nodes and interaction edges from a Python file.

    Args:
        source: The Python source code.
        file_path: The file path.
        structural_nodes: Previously extracted structural nodes.
        stmt_nodes: Optional statement nodes for PART_OF linking.
        tree: Optional pre-parsed tree-sitter Tree. If None, parses source internally.

    Returns:
        VariableResult with all variable nodes and edges.
    """
    if tree is None:
        parser = _get_parser()
        tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node

    variables: dict[str, VariableNode] = {}
    edges: list[VariableEdge] = []

    func_nodes = [n for n in structural_nodes if n.node_type == "Function"]

    def _find_and_extract(ts_node: tree_sitter.Node) -> None:
        """Walk AST to find functions and extract variable interactions."""
        for child in ts_node.children:
            actual = child
            if child.type == "decorated_definition":
                for sub in child.children:
                    if sub.type in ("function_definition", "class_definition"):
                        actual = sub
                        break
                else:
                    continue

            if actual.type == "function_definition":
                func_line = actual.start_point[0] + 1
                matched = None
                for fn in func_nodes:
                    if fn.start_line == func_line:
                        matched = fn
                        break

                if matched:
                    class_name = _find_enclosing_class(matched.name, structural_nodes)
                    _extract_from_function(
                        actual, matched.name, class_name, file_path,
                        variables, edges, stmt_nodes or [],
                    )

                body = actual.child_by_field_name("body")
                if body:
                    _find_and_extract(body)

            elif actual.type == "class_definition":
                body = actual.child_by_field_name("body")
                if body:
                    _find_and_extract(body)

    _find_and_extract(root)

    return VariableResult(nodes=list(variables.values()), edges=edges)
