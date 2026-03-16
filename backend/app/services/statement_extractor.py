"""Extract Statement, ControlFlow, and Branch nodes with CONTAINS and NEXT edges."""

from __future__ import annotations

from dataclasses import dataclass, field

import tree_sitter

from app.services.ast_parser import ParsedNode, _get_parser


# Statement kinds that map to tree-sitter node types
_STATEMENT_KIND_MAP: dict[str, str] = {
    "expression_statement": "expression",
    "return_statement": "return",
    "yield": "yield",
    "raise_statement": "raise",
    "assert_statement": "assert",
    "pass_statement": "pass",
    "delete_statement": "delete",
    "global_statement": "global",
    "nonlocal_statement": "nonlocal",
    "assignment": "assignment",
    "augmented_assignment": "assignment",
    "type_alias_statement": "assignment",
}

# Control flow node types
_CONTROL_FLOW_TYPES: set[str] = {
    "if_statement",
    "for_statement",
    "while_statement",
    "try_statement",
    "with_statement",
}

_CONTROL_FLOW_KIND_MAP: dict[str, str] = {
    "if_statement": "if",
    "for_statement": "for",
    "while_statement": "while",
    "try_statement": "try",
    "with_statement": "with",
}


@dataclass
class StatementNode:
    """Represents a Statement, ControlFlow, or Branch node.

    Attributes:
        node_type: One of "Statement", "ControlFlow", "Branch".
        name: Unique identifier (e.g., "module.func.stmt_0").
        kind: Statement kind (assignment, expression, return, etc.) or control flow kind.
        source_text: Raw source text.
        start_line: 1-based start line.
        end_line: 1-based end line.
        start_col: 0-based start column.
        end_col: 0-based end column.
        seq: Position among siblings in parent body.
        module_path: File path for re-indexing.
        condition_text: Condition/iterator expression for ControlFlow/Branch nodes.
        parent_name: Qualified name of the parent node.
    """

    node_type: str
    name: str
    kind: str
    source_text: str
    start_line: int
    end_line: int
    start_col: int
    end_col: int
    seq: int
    module_path: str
    condition_text: str | None = None
    parent_name: str | None = None


@dataclass
class StatementEdge:
    """Represents a CONTAINS or NEXT edge.

    Attributes:
        edge_type: One of "CONTAINS", "NEXT".
        source_name: Name of the source node.
        target_name: Name of the target node.
        source_type: Node type of source.
        target_type: Node type of target.
    """

    edge_type: str
    source_name: str
    target_name: str
    source_type: str
    target_type: str


@dataclass
class StatementResult:
    """Result of statement extraction for a file.

    Attributes:
        nodes: All extracted statement-level nodes.
        edges: All CONTAINS and NEXT edges.
    """

    nodes: list[StatementNode]
    edges: list[StatementEdge]


def _get_condition_text(node: tree_sitter.Node) -> str | None:
    """Extract the condition or iterator expression from a control flow node.

    Args:
        node: A tree-sitter control flow node.

    Returns:
        The condition text, or None.
    """
    if node.type == "if_statement":
        cond = node.child_by_field_name("condition")
        if cond:
            return cond.text.decode("utf-8")
    elif node.type == "while_statement":
        cond = node.child_by_field_name("condition")
        if cond:
            return cond.text.decode("utf-8")
    elif node.type == "for_statement":
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left and right:
            return f"{left.text.decode('utf-8')} in {right.text.decode('utf-8')}"
    elif node.type == "with_statement":
        # Get the with items
        for child in node.children:
            if child.type == "with_clause":
                return child.text.decode("utf-8")
        # Fallback: get items between "with" and ":"
        items = []
        for child in node.children:
            if child.type in ("with", ":"):
                continue
            if child.type == "block":
                break
            items.append(child.text.decode("utf-8"))
        if items:
            return " ".join(items)
    return None


def _is_statement(node: tree_sitter.Node) -> bool:
    """Check if a tree-sitter node is a statement we should extract."""
    return node.type in _STATEMENT_KIND_MAP


def _is_control_flow(node: tree_sitter.Node) -> bool:
    """Check if a tree-sitter node is a control flow structure."""
    return node.type in _CONTROL_FLOW_TYPES


def _get_statement_kind(node: tree_sitter.Node) -> str:
    """Get the kind string for a statement node."""
    # expression_statement may wrap an assignment
    if node.type == "expression_statement" and node.named_children:
        inner = node.named_children[0]
        if inner.type in ("assignment", "augmented_assignment"):
            return "assignment"
        if inner.type == "yield":
            return "yield"
    return _STATEMENT_KIND_MAP.get(node.type, "expression")


def _extract_branches(
    cf_node: tree_sitter.Node,
    cf_name: str,
    module_path: str,
    nodes: list[StatementNode],
    edges: list[StatementEdge],
) -> None:
    """Extract Branch nodes from a ControlFlow node and recurse into their bodies.

    Args:
        cf_node: The control flow tree-sitter node.
        cf_name: Qualified name of the ControlFlow node.
        module_path: File path.
        nodes: Accumulator for extracted nodes.
        edges: Accumulator for extracted edges.
    """
    if cf_node.type == "if_statement":
        _extract_if_branches(cf_node, cf_name, module_path, nodes, edges)
    elif cf_node.type == "for_statement":
        _extract_loop_body(cf_node, cf_name, "for", module_path, nodes, edges)
    elif cf_node.type == "while_statement":
        _extract_loop_body(cf_node, cf_name, "while", module_path, nodes, edges)
    elif cf_node.type == "try_statement":
        _extract_try_branches(cf_node, cf_name, module_path, nodes, edges)
    elif cf_node.type == "with_statement":
        _extract_with_body(cf_node, cf_name, module_path, nodes, edges)


def _extract_if_branches(
    node: tree_sitter.Node,
    cf_name: str,
    module_path: str,
    nodes: list[StatementNode],
    edges: list[StatementEdge],
) -> None:
    """Extract branches from an if/elif/else statement."""
    branch_seq = 0

    # The "if" branch
    cond = node.child_by_field_name("condition")
    consequence = node.child_by_field_name("consequence")
    if consequence:
        branch_name = f"{cf_name}.branch_{branch_seq}"
        cond_text = cond.text.decode("utf-8") if cond else None
        branch = StatementNode(
            node_type="Branch",
            name=branch_name,
            kind="if",
            source_text=consequence.text.decode("utf-8"),
            start_line=consequence.start_point[0] + 1,
            end_line=consequence.end_point[0] + 1,
            start_col=consequence.start_point[1],
            end_col=consequence.end_point[1],
            seq=branch_seq,
            module_path=module_path,
            condition_text=cond_text,
            parent_name=cf_name,
        )
        nodes.append(branch)
        edges.append(StatementEdge("CONTAINS", cf_name, branch_name, "ControlFlow", "Branch"))
        _extract_body_statements(consequence, branch_name, "Branch", module_path, nodes, edges)
        branch_seq += 1

    # elif and else branches
    for child in node.children:
        if child.type == "elif_clause":
            elif_cond = child.child_by_field_name("condition")
            elif_body = child.child_by_field_name("consequence")
            if elif_body:
                branch_name = f"{cf_name}.branch_{branch_seq}"
                cond_text = elif_cond.text.decode("utf-8") if elif_cond else None
                branch = StatementNode(
                    node_type="Branch",
                    name=branch_name,
                    kind="elif",
                    source_text=elif_body.text.decode("utf-8"),
                    start_line=elif_body.start_point[0] + 1,
                    end_line=elif_body.end_point[0] + 1,
                    start_col=elif_body.start_point[1],
                    end_col=elif_body.end_point[1],
                    seq=branch_seq,
                    module_path=module_path,
                    condition_text=cond_text,
                    parent_name=cf_name,
                )
                nodes.append(branch)
                edges.append(StatementEdge("CONTAINS", cf_name, branch_name, "ControlFlow", "Branch"))
                _extract_body_statements(elif_body, branch_name, "Branch", module_path, nodes, edges)
                branch_seq += 1

        elif child.type == "else_clause":
            else_body = child.child_by_field_name("body")
            if else_body:
                branch_name = f"{cf_name}.branch_{branch_seq}"
                branch = StatementNode(
                    node_type="Branch",
                    name=branch_name,
                    kind="else",
                    source_text=else_body.text.decode("utf-8"),
                    start_line=else_body.start_point[0] + 1,
                    end_line=else_body.end_point[0] + 1,
                    start_col=else_body.start_point[1],
                    end_col=else_body.end_point[1],
                    seq=branch_seq,
                    module_path=module_path,
                    condition_text=None,
                    parent_name=cf_name,
                )
                nodes.append(branch)
                edges.append(StatementEdge("CONTAINS", cf_name, branch_name, "ControlFlow", "Branch"))
                _extract_body_statements(else_body, branch_name, "Branch", module_path, nodes, edges)
                branch_seq += 1


def _extract_loop_body(
    node: tree_sitter.Node,
    cf_name: str,
    kind: str,
    module_path: str,
    nodes: list[StatementNode],
    edges: list[StatementEdge],
) -> None:
    """Extract the body of a for/while loop as a branch."""
    body = node.child_by_field_name("body")
    if body:
        branch_name = f"{cf_name}.branch_0"
        branch = StatementNode(
            node_type="Branch",
            name=branch_name,
            kind=kind,
            source_text=body.text.decode("utf-8"),
            start_line=body.start_point[0] + 1,
            end_line=body.end_point[0] + 1,
            start_col=body.start_point[1],
            end_col=body.end_point[1],
            seq=0,
            module_path=module_path,
            condition_text=None,
            parent_name=cf_name,
        )
        nodes.append(branch)
        edges.append(StatementEdge("CONTAINS", cf_name, branch_name, "ControlFlow", "Branch"))
        _extract_body_statements(body, branch_name, "Branch", module_path, nodes, edges)

    # Check for else clause on loop
    for child in node.children:
        if child.type == "else_clause":
            else_body = child.child_by_field_name("body")
            if else_body:
                branch_name = f"{cf_name}.branch_1"
                branch = StatementNode(
                    node_type="Branch",
                    name=branch_name,
                    kind="else",
                    source_text=else_body.text.decode("utf-8"),
                    start_line=else_body.start_point[0] + 1,
                    end_line=else_body.end_point[0] + 1,
                    start_col=else_body.start_point[1],
                    end_col=else_body.end_point[1],
                    seq=1,
                    module_path=module_path,
                    condition_text=None,
                    parent_name=cf_name,
                )
                nodes.append(branch)
                edges.append(StatementEdge("CONTAINS", cf_name, branch_name, "ControlFlow", "Branch"))
                _extract_body_statements(else_body, branch_name, "Branch", module_path, nodes, edges)


def _extract_try_branches(
    node: tree_sitter.Node,
    cf_name: str,
    module_path: str,
    nodes: list[StatementNode],
    edges: list[StatementEdge],
) -> None:
    """Extract branches from a try/except/else/finally statement."""
    branch_seq = 0

    body = node.child_by_field_name("body")
    if body:
        branch_name = f"{cf_name}.branch_{branch_seq}"
        branch = StatementNode(
            node_type="Branch",
            name=branch_name,
            kind="try",
            source_text=body.text.decode("utf-8"),
            start_line=body.start_point[0] + 1,
            end_line=body.end_point[0] + 1,
            start_col=body.start_point[1],
            end_col=body.end_point[1],
            seq=branch_seq,
            module_path=module_path,
            condition_text=None,
            parent_name=cf_name,
        )
        nodes.append(branch)
        edges.append(StatementEdge("CONTAINS", cf_name, branch_name, "ControlFlow", "Branch"))
        _extract_body_statements(body, branch_name, "Branch", module_path, nodes, edges)
        branch_seq += 1

    for child in node.children:
        if child.type == "except_clause":
            # Get the exception type if present
            except_cond = None
            for sub in child.children:
                if sub.type not in ("except", ":", "block", "as", "identifier"):
                    except_cond = sub.text.decode("utf-8")
                    break

            except_body = None
            for sub in child.children:
                if sub.type == "block":
                    except_body = sub
                    break

            if except_body:
                branch_name = f"{cf_name}.branch_{branch_seq}"
                branch = StatementNode(
                    node_type="Branch",
                    name=branch_name,
                    kind="except",
                    source_text=except_body.text.decode("utf-8"),
                    start_line=except_body.start_point[0] + 1,
                    end_line=except_body.end_point[0] + 1,
                    start_col=except_body.start_point[1],
                    end_col=except_body.end_point[1],
                    seq=branch_seq,
                    module_path=module_path,
                    condition_text=except_cond,
                    parent_name=cf_name,
                )
                nodes.append(branch)
                edges.append(StatementEdge("CONTAINS", cf_name, branch_name, "ControlFlow", "Branch"))
                _extract_body_statements(except_body, branch_name, "Branch", module_path, nodes, edges)
                branch_seq += 1

        elif child.type == "else_clause":
            else_body = child.child_by_field_name("body")
            if else_body:
                branch_name = f"{cf_name}.branch_{branch_seq}"
                branch = StatementNode(
                    node_type="Branch",
                    name=branch_name,
                    kind="else",
                    source_text=else_body.text.decode("utf-8"),
                    start_line=else_body.start_point[0] + 1,
                    end_line=else_body.end_point[0] + 1,
                    start_col=else_body.start_point[1],
                    end_col=else_body.end_point[1],
                    seq=branch_seq,
                    module_path=module_path,
                    condition_text=None,
                    parent_name=cf_name,
                )
                nodes.append(branch)
                edges.append(StatementEdge("CONTAINS", cf_name, branch_name, "ControlFlow", "Branch"))
                _extract_body_statements(else_body, branch_name, "Branch", module_path, nodes, edges)
                branch_seq += 1

        elif child.type == "finally_clause":
            finally_body = None
            for sub in child.children:
                if sub.type == "block":
                    finally_body = sub
                    break

            if finally_body:
                branch_name = f"{cf_name}.branch_{branch_seq}"
                branch = StatementNode(
                    node_type="Branch",
                    name=branch_name,
                    kind="finally",
                    source_text=finally_body.text.decode("utf-8"),
                    start_line=finally_body.start_point[0] + 1,
                    end_line=finally_body.end_point[0] + 1,
                    start_col=finally_body.start_point[1],
                    end_col=finally_body.end_point[1],
                    seq=branch_seq,
                    module_path=module_path,
                    condition_text=None,
                    parent_name=cf_name,
                )
                nodes.append(branch)
                edges.append(StatementEdge("CONTAINS", cf_name, branch_name, "ControlFlow", "Branch"))
                _extract_body_statements(finally_body, branch_name, "Branch", module_path, nodes, edges)
                branch_seq += 1


def _extract_with_body(
    node: tree_sitter.Node,
    cf_name: str,
    module_path: str,
    nodes: list[StatementNode],
    edges: list[StatementEdge],
) -> None:
    """Extract the body of a with statement as a branch."""
    body = node.child_by_field_name("body")
    if body:
        branch_name = f"{cf_name}.branch_0"
        branch = StatementNode(
            node_type="Branch",
            name=branch_name,
            kind="with",
            source_text=body.text.decode("utf-8"),
            start_line=body.start_point[0] + 1,
            end_line=body.end_point[0] + 1,
            start_col=body.start_point[1],
            end_col=body.end_point[1],
            seq=0,
            module_path=module_path,
            condition_text=None,
            parent_name=cf_name,
        )
        nodes.append(branch)
        edges.append(StatementEdge("CONTAINS", cf_name, branch_name, "ControlFlow", "Branch"))
        _extract_body_statements(body, branch_name, "Branch", module_path, nodes, edges)


def _extract_body_statements(
    body_node: tree_sitter.Node,
    parent_name: str,
    parent_type: str,
    module_path: str,
    nodes: list[StatementNode],
    edges: list[StatementEdge],
) -> None:
    """Extract statements and control flow from a body block.

    Creates Statement/ControlFlow nodes, CONTAINS edges to parent, and NEXT edges
    between sequential siblings.

    Args:
        body_node: The block/body tree-sitter node.
        parent_name: Qualified name of the parent.
        parent_type: Node type of the parent.
        module_path: File path.
        nodes: Accumulator for extracted nodes.
        edges: Accumulator for extracted edges.
    """
    prev_name: str | None = None
    prev_type: str | None = None
    seq = 0

    for child in body_node.named_children:
        # Skip docstrings (first expression_statement with string)
        if seq == 0 and child.type == "expression_statement" and parent_type in ("Function", "Class"):
            if child.named_children and child.named_children[0].type == "string":
                continue

        # Skip nested function/class definitions (already handled by structural parser)
        if child.type in ("function_definition", "class_definition", "decorated_definition"):
            continue

        if _is_control_flow(child):
            cf_kind = _CONTROL_FLOW_KIND_MAP[child.type]
            cf_name = f"{parent_name}.cf_{seq}"
            cond_text = _get_condition_text(child)

            cf_node = StatementNode(
                node_type="ControlFlow",
                name=cf_name,
                kind=cf_kind,
                source_text=child.text.decode("utf-8"),
                start_line=child.start_point[0] + 1,
                end_line=child.end_point[0] + 1,
                start_col=child.start_point[1],
                end_col=child.end_point[1],
                seq=seq,
                module_path=module_path,
                condition_text=cond_text,
                parent_name=parent_name,
            )
            nodes.append(cf_node)
            edges.append(StatementEdge("CONTAINS", parent_name, cf_name, parent_type, "ControlFlow"))

            # NEXT edge from previous sibling
            if prev_name is not None and prev_type is not None:
                edges.append(StatementEdge("NEXT", prev_name, cf_name, prev_type, "ControlFlow"))

            prev_name = cf_name
            prev_type = "ControlFlow"

            # Extract branches
            _extract_branches(child, cf_name, module_path, nodes, edges)

        elif _is_statement(child):
            stmt_kind = _get_statement_kind(child)
            stmt_name = f"{parent_name}.stmt_{seq}"

            stmt_node = StatementNode(
                node_type="Statement",
                name=stmt_name,
                kind=stmt_kind,
                source_text=child.text.decode("utf-8"),
                start_line=child.start_point[0] + 1,
                end_line=child.end_point[0] + 1,
                start_col=child.start_point[1],
                end_col=child.end_point[1],
                seq=seq,
                module_path=module_path,
                parent_name=parent_name,
            )
            nodes.append(stmt_node)
            edges.append(StatementEdge("CONTAINS", parent_name, stmt_name, parent_type, "Statement"))

            # NEXT edge from previous sibling
            if prev_name is not None and prev_type is not None:
                edges.append(StatementEdge("NEXT", prev_name, stmt_name, prev_type, "Statement"))

            prev_name = stmt_name
            prev_type = "Statement"

        seq += 1


def extract_statements(
    source: str,
    file_path: str,
    structural_nodes: list[ParsedNode],
    tree: tree_sitter.Tree | None = None,
) -> StatementResult:
    """Extract all statement-level nodes and edges from a Python file.

    For each function in the structural nodes, walks its body to create
    Statement, ControlFlow, and Branch nodes with CONTAINS and NEXT edges.

    Args:
        source: The Python source code.
        file_path: The file path.
        structural_nodes: Previously extracted structural nodes.
        tree: Optional pre-parsed tree-sitter Tree. If None, parses source internally.

    Returns:
        StatementResult with all statement-level nodes and edges.
    """
    if tree is None:
        parser = _get_parser()
        tree = parser.parse(source.encode("utf-8"))
    root = tree.root_node

    all_nodes: list[StatementNode] = []
    all_edges: list[StatementEdge] = []

    # Build a map of function qualified names to their line numbers
    func_nodes = [n for n in structural_nodes if n.node_type == "Function"]

    def _find_function_defs(ts_node: tree_sitter.Node) -> None:
        """Walk the AST to find function definitions and extract their statements."""
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
                # Match to structural node
                matched = None
                for fn in func_nodes:
                    if fn.start_line == func_line:
                        matched = fn
                        break

                if matched:
                    body = actual.child_by_field_name("body")
                    if body:
                        _extract_body_statements(
                            body, matched.name, "Function", file_path, all_nodes, all_edges
                        )

                # Recurse into nested definitions
                body = actual.child_by_field_name("body")
                if body:
                    _find_function_defs(body)

            elif actual.type == "class_definition":
                body = actual.child_by_field_name("body")
                if body:
                    _find_function_defs(body)

    _find_function_defs(root)

    return StatementResult(nodes=all_nodes, edges=all_edges)
