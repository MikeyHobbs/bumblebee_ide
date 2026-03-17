"""Extract PASSES_TO and FEEDS edges for cross-function and intra-function data flow."""

from __future__ import annotations

from dataclasses import dataclass, field

import tree_sitter

from app.services.parsing.ast_parser import ParsedNode, _get_parser
from app.services.parsing.relationship_extractor import RelationshipEdge
from app.services.parsing.variable_extractor import VariableNode, VariableEdge


@dataclass
class DataFlowEdge:
    """Represents a PASSES_TO or FEEDS edge.

    Attributes:
        edge_type: One of "PASSES_TO", "FEEDS".
        source_name: Name of the source Variable node.
        target_name: Name of the target Variable node.
        properties: Additional edge properties.
    """

    edge_type: str
    source_name: str
    target_name: str
    properties: dict[str, str | int | None] = field(default_factory=dict)


@dataclass
class DataFlowResult:
    """Result of data flow extraction.

    Attributes:
        edges: All PASSES_TO and FEEDS edges.
    """

    edges: list[DataFlowEdge]


def extract_passes_to(
    call_edges: list[RelationshipEdge],
    variable_nodes: list[VariableNode],
    structural_nodes: list[ParsedNode],
    source: str,
    file_path: str,
    tree: tree_sitter.Tree | None = None,
) -> list[DataFlowEdge]:
    """Extract PASSES_TO edges by matching call arguments to callee parameters.

    For each CALLS edge, finds the arguments at the call site and matches them
    to the callee's parameter Variable nodes.

    Args:
        call_edges: CALLS edges from relationship extraction.
        variable_nodes: All Variable nodes.
        structural_nodes: Structural nodes (for parameter info).
        source: Source code text.
        file_path: File path.
        tree: Optional pre-parsed tree-sitter Tree. If None, parses source internally.

    Returns:
        List of PASSES_TO edges.
    """
    if tree is None:
        parser = _get_parser()
        tree = parser.parse(source.encode("utf-8"))

    var_map = {v.name: v for v in variable_nodes}
    func_map = {n.name: n for n in structural_nodes if n.node_type == "Function"}

    edges: list[DataFlowEdge] = []

    for call_edge in call_edges:
        if call_edge.edge_type != "CALLS":
            continue

        caller_name = call_edge.source_name
        callee_name = call_edge.target_name
        call_line = call_edge.properties.get("call_line", 0)
        call_seq = call_edge.properties.get("seq", 0)

        callee_func = func_map.get(callee_name)
        if callee_func is None:
            continue

        # Get callee parameter names (skip self/cls)
        callee_params = [p for p in callee_func.params if p not in ("self", "cls")]

        # Find the call node in the AST at the call_line
        call_args = _find_call_arguments(tree.root_node, int(call_line) if call_line else 0)  # type: ignore[arg-type]
        if not call_args:
            continue

        # Match positional arguments
        for i, (arg_text, arg_keyword) in enumerate(call_args):
            # Determine which parameter this argument maps to
            target_param: str | None = None
            if arg_keyword:
                # Keyword argument
                if arg_keyword in callee_params:
                    target_param = arg_keyword
            elif i < len(callee_params):
                target_param = callee_params[i]

            if target_param is None:
                continue

            # Find the caller's variable that's being passed
            # The arg_text might be a variable name
            source_var_name = f"{caller_name}.{arg_text}"
            if source_var_name not in var_map:
                # Try self.x resolution
                if arg_text.startswith("self."):
                    # Find class name
                    parts = caller_name.rsplit(".", 1)
                    if len(parts) > 1:
                        class_candidate = f"{parts[0]}.{arg_text.replace('self.', '')}"
                        if class_candidate in var_map:
                            source_var_name = class_candidate
                        else:
                            continue
                    else:
                        continue
                else:
                    continue

            # Find the callee's parameter variable
            target_var_name = f"{callee_name}.{target_param}"
            if target_var_name not in var_map:
                continue

            edges.append(DataFlowEdge(
                edge_type="PASSES_TO",
                source_name=source_var_name,
                target_name=target_var_name,
                properties={
                    "call_line": call_line,
                    "seq": call_seq,
                    "arg_position": i,
                    "arg_keyword": arg_keyword,
                },
            ))

    return edges


def _find_call_arguments(
    root: tree_sitter.Node,
    target_line: int,
) -> list[tuple[str, str | None]]:
    """Find call arguments at a specific line.

    Args:
        root: Root tree-sitter node.
        target_line: 1-based line number to find.

    Returns:
        List of (arg_text, keyword_or_none) tuples.
    """
    results: list[tuple[str, str | None]] = []

    def _walk(node: tree_sitter.Node) -> bool:
        if node.type == "call" and node.start_point[0] + 1 == target_line:
            args_node = node.child_by_field_name("arguments")
            if args_node:
                for arg in args_node.named_children:
                    if arg.type == "keyword_argument":
                        name = arg.child_by_field_name("name")
                        value = arg.child_by_field_name("value")
                        if name and value:
                            results.append((value.text.decode("utf-8"), name.text.decode("utf-8")))
                    elif arg.type == "list_splat":
                        # *args
                        results.append((arg.text.decode("utf-8"), None))
                    elif arg.type == "dictionary_splat":
                        # **kwargs
                        results.append((arg.text.decode("utf-8"), None))
                    else:
                        results.append((arg.text.decode("utf-8"), None))
            return True

        for child in node.children:
            if _walk(child):
                return True
        return False

    _walk(root)
    return results


def extract_feeds(
    variable_edges: list[VariableEdge],
    variable_nodes: list[VariableNode],
    source: str,
    file_path: str,
    structural_nodes: list[ParsedNode],
    tree: tree_sitter.Tree | None = None,
) -> list[DataFlowEdge]:
    """Extract FEEDS edges: when a read of one variable feeds into assignment/mutation of another.

    Args:
        variable_edges: All variable interaction edges (ASSIGNS, MUTATES, READS).
        variable_nodes: All Variable nodes.
        source: Source code text.
        file_path: File path.
        structural_nodes: Structural nodes.
        tree: Optional pre-parsed tree-sitter Tree. If None, parses source internally.

    Returns:
        List of FEEDS edges.
    """
    if tree is not None:
        pass  # tree not used by extract_feeds but accepted for API consistency
    # No tree-sitter usage in this function — the original parsed but never used it

    var_map = {v.name: v for v in variable_nodes}
    func_map = {n.name: n for n in structural_nodes if n.node_type == "Function"}

    edges: list[DataFlowEdge] = []

    # Group edges by function
    func_edges: dict[str, list[VariableEdge]] = {}
    for edge in variable_edges:
        func_name = edge.source_name
        if func_name not in func_edges:
            func_edges[func_name] = []
        func_edges[func_name].append(edge)

    for func_name, func_edge_list in func_edges.items():
        # For each assignment, find reads in the RHS that feed into the assigned variable
        assigns = [e for e in func_edge_list if e.edge_type == "ASSIGNS"]
        mutates = [e for e in func_edge_list if e.edge_type == "MUTATES"]
        reads = [e for e in func_edge_list if e.edge_type == "READS"]

        # Build a line-based index of reads
        reads_by_line: dict[int, list[VariableEdge]] = {}
        for read in reads:
            line = read.properties.get("line", 0)
            if line:
                if line not in reads_by_line:
                    reads_by_line[line] = []
                reads_by_line[line].append(read)

        # For each assignment, check if reads on the same line feed into it
        for assign in assigns:
            assign_line = assign.properties.get("line", 0)
            assign_seq = assign.properties.get("seq", 0)
            target_var = assign.target_name
            if not assign_line:
                continue

            # Find reads on the same line that are NOT the target variable
            line_reads = reads_by_line.get(assign_line, [])  # type: ignore[arg-type]
            for read in line_reads:
                if read.target_name != target_var:
                    edges.append(DataFlowEdge(
                        edge_type="FEEDS",
                        source_name=read.target_name,
                        target_name=target_var,
                        properties={
                            "line": assign_line,
                            "seq": assign_seq,
                            "expression_text": "",
                            "via": "assignment",
                        },
                    ))

        # For each mutation, check if reads in the arguments feed into the mutated variable
        for mutate in mutates:
            mutate_line = mutate.properties.get("line", 0)
            mutate_seq = mutate.properties.get("seq", 0)
            target_var = mutate.target_name
            if not mutate_line:
                continue

            line_reads = reads_by_line.get(mutate_line, [])  # type: ignore[arg-type]
            for read in line_reads:
                if read.target_name != target_var:
                    edges.append(DataFlowEdge(
                        edge_type="FEEDS",
                        source_name=read.target_name,
                        target_name=target_var,
                        properties={
                            "line": mutate_line,
                            "seq": mutate_seq,
                            "expression_text": "",
                            "via": "mutation_arg",
                        },
                    ))

    return edges


def extract_dataflow(
    source: str,
    file_path: str,
    structural_nodes: list[ParsedNode],
    call_edges: list[RelationshipEdge],
    variable_nodes: list[VariableNode],
    variable_edges: list[VariableEdge],
    tree: tree_sitter.Tree | None = None,
) -> DataFlowResult:
    """Extract all data flow edges (PASSES_TO and FEEDS).

    Args:
        source: Source code text.
        file_path: File path.
        structural_nodes: Structural nodes.
        call_edges: CALLS relationship edges.
        variable_nodes: Variable nodes.
        variable_edges: Variable interaction edges.
        tree: Optional pre-parsed tree-sitter Tree. If None, parses source internally.

    Returns:
        DataFlowResult with all data flow edges.
    """
    all_edges: list[DataFlowEdge] = []

    # PASSES_TO: cross-function argument passing
    passes_to = extract_passes_to(call_edges, variable_nodes, structural_nodes, source, file_path, tree=tree)
    all_edges.extend(passes_to)

    # FEEDS: intra-function data flow
    feeds = extract_feeds(variable_edges, variable_nodes, source, file_path, structural_nodes, tree=tree)
    all_edges.extend(feeds)

    return DataFlowResult(edges=all_edges)
