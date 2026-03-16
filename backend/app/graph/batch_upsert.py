"""Batch upserter for FalkorDB — collects entities and flushes in ~16 UNWIND queries."""

from __future__ import annotations

import logging

from app.graph import queries
from app.services.ast_parser import ParsedEdge, ParsedNode
from app.services.dataflow_extractor import DataFlowEdge
from app.services.relationship_extractor import RelationshipEdge
from app.services.statement_extractor import StatementEdge, StatementNode
from app.services.variable_extractor import VariableEdge, VariableNode

logger = logging.getLogger(__name__)


class BatchUpserter:
    """Collects graph entities for a file, then flushes them in batched UNWIND queries.

    Instead of issuing ~300+ individual graph.query() calls per file, this class
    accumulates all nodes and edges, then writes them in ~16 bulk operations.

    Args:
        graph: FalkorDB graph instance.
    """

    def __init__(self, graph) -> None:  # type: ignore[no-untyped-def]
        self._graph = graph
        self._modules: list[dict[str, object]] = []
        self._classes: list[dict[str, object]] = []
        self._functions: list[dict[str, object]] = []
        self._defines: list[dict[str, object]] = []
        self._calls: list[dict[str, object]] = []
        self._inherits: list[dict[str, object]] = []
        self._imports: list[dict[str, object]] = []
        self._statements: list[dict[str, object]] = []
        self._control_flows: list[dict[str, object]] = []
        self._branches: list[dict[str, object]] = []
        self._contains: list[dict[str, object]] = []
        self._next: list[dict[str, object]] = []
        self._variables: list[dict[str, object]] = []
        self._assigns: list[dict[str, object]] = []
        self._mutates: list[dict[str, object]] = []
        self._reads: list[dict[str, object]] = []
        self._returns: list[dict[str, object]] = []
        self._passes_to: list[dict[str, object]] = []
        self._feeds: list[dict[str, object]] = []

    def add_node(self, node: ParsedNode, checksum: str = "") -> None:
        """Add a structural node (Module, Class, or Function) to the batch.

        Args:
            node: Parsed AST node.
            checksum: File checksum (used for Module nodes).
        """
        if node.node_type == "Module":
            self._modules.append({
                "name": node.name,
                "start_line": node.start_line,
                "end_line": node.end_line,
                "module_path": node.module_path,
                "checksum": checksum,
            })
        elif node.node_type == "Class":
            self._classes.append({
                "name": node.name,
                "start_line": node.start_line,
                "end_line": node.end_line,
                "start_col": node.start_col,
                "end_col": node.end_col,
                "source_text": node.source_text,
                "module_path": node.module_path,
                "decorators": node.decorators,
                "docstring": node.docstring or "",
            })
        elif node.node_type == "Function":
            self._functions.append({
                "name": node.name,
                "start_line": node.start_line,
                "end_line": node.end_line,
                "start_col": node.start_col,
                "end_col": node.end_col,
                "source_text": node.source_text,
                "module_path": node.module_path,
                "params": node.params,
                "decorators": node.decorators,
                "docstring": node.docstring or "",
                "is_async": node.is_async,
            })

    def add_edge(self, edge: ParsedEdge) -> None:
        """Add a DEFINES edge to the batch.

        Args:
            edge: Parsed structural edge.
        """
        if edge.edge_type == "DEFINES":
            self._defines.append({
                "source_name": edge.source_name,
                "target_name": edge.target_name,
            })

    def add_relationship_edge(self, edge: RelationshipEdge) -> None:
        """Add a relationship edge (CALLS, INHERITS, IMPORTS) to the batch.

        Args:
            edge: Relationship edge.
        """
        if edge.edge_type == "CALLS":
            self._calls.append({
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "call_line": edge.properties.get("call_line", 0),
                "seq": edge.properties.get("seq", 0),
                "call_order": edge.properties.get("call_order", 0),
            })
        elif edge.edge_type == "INHERITS":
            self._inherits.append({
                "source_name": edge.source_name,
                "target_name": edge.target_name,
            })
        elif edge.edge_type == "IMPORTS":
            self._imports.append({
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "alias": edge.properties.get("alias") or "",
            })

    def add_statement_node(self, node: StatementNode) -> None:
        """Add a Statement, ControlFlow, or Branch node to the batch.

        Args:
            node: Statement-level node.
        """
        item = {
            "name": node.name,
            "kind": node.kind,
            "source_text": node.source_text,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "start_col": node.start_col,
            "end_col": node.end_col,
            "seq": node.seq,
            "module_path": node.module_path,
            "condition_text": node.condition_text or "",
        }
        if node.node_type == "Statement":
            self._statements.append(item)
        elif node.node_type == "ControlFlow":
            self._control_flows.append(item)
        elif node.node_type == "Branch":
            self._branches.append(item)

    def add_statement_edge(self, edge: StatementEdge) -> None:
        """Add a CONTAINS or NEXT edge to the batch.

        Args:
            edge: Statement-level edge.
        """
        item = {"source_name": edge.source_name, "target_name": edge.target_name}
        if edge.edge_type == "CONTAINS":
            self._contains.append(item)
        elif edge.edge_type == "NEXT":
            self._next.append(item)

    def add_variable_node(self, node: VariableNode) -> None:
        """Add a Variable node to the batch.

        Args:
            node: Variable node.
        """
        self._variables.append({
            "name": node.name,
            "scope": node.scope,
            "origin_line": node.origin_line,
            "origin_func": node.origin_func,
            "type_hint": node.type_hint or "",
            "module_path": node.module_path,
        })

    def add_variable_edge(self, edge: VariableEdge) -> None:
        """Add a variable interaction edge (ASSIGNS, MUTATES, READS, RETURNS) to the batch.

        Args:
            edge: Variable interaction edge.
        """
        props = edge.properties
        if edge.edge_type == "ASSIGNS":
            self._assigns.append({
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "line": props.get("line", 0),
                "col": props.get("col", 0),
                "seq": props.get("seq", 0),
                "is_rebind": props.get("is_rebind", False),
                "control_context": props.get("control_context") or "",
                "branch": props.get("branch") or "",
            })
        elif edge.edge_type == "MUTATES":
            self._mutates.append({
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "line": props.get("line", 0),
                "seq": props.get("seq", 0),
                "mutation_kind": props.get("mutation_kind", ""),
                "control_context": props.get("control_context") or "",
                "branch": props.get("branch") or "",
            })
        elif edge.edge_type == "READS":
            self._reads.append({
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "line": props.get("line", 0),
                "seq": props.get("seq", 0),
                "control_context": props.get("control_context") or "",
                "branch": props.get("branch") or "",
            })
        elif edge.edge_type == "RETURNS":
            self._returns.append({
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "line": props.get("line", 0),
                "seq": props.get("seq", 0),
                "control_context": props.get("control_context") or "",
                "branch": props.get("branch") or "",
            })

    def add_dataflow_edge(self, edge: DataFlowEdge) -> None:
        """Add a PASSES_TO or FEEDS edge to the batch.

        Args:
            edge: Data flow edge.
        """
        props = edge.properties
        if edge.edge_type == "PASSES_TO":
            self._passes_to.append({
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "call_line": props.get("call_line", 0),
                "seq": props.get("seq", 0),
                "arg_position": props.get("arg_position", 0),
                "arg_keyword": props.get("arg_keyword") or "",
            })
        elif edge.edge_type == "FEEDS":
            self._feeds.append({
                "source_name": edge.source_name,
                "target_name": edge.target_name,
                "line": props.get("line", 0),
                "seq": props.get("seq", 0),
                "expression_text": props.get("expression_text") or "",
                "via": props.get("via") or "",
            })

    def flush(self) -> int:
        """Execute all batched UNWIND queries. Returns total query count."""
        count = 0
        batch_map: list[tuple[str, list[dict[str, object]]]] = [
            (queries.BATCH_MERGE_MODULES, self._modules),
            (queries.BATCH_MERGE_CLASSES, self._classes),
            (queries.BATCH_MERGE_FUNCTIONS, self._functions),
            (queries.BATCH_MERGE_DEFINES, self._defines),
            (queries.BATCH_MERGE_CALLS, self._calls),
            (queries.BATCH_MERGE_INHERITS, self._inherits),
            (queries.BATCH_MERGE_IMPORTS, self._imports),
            (queries.BATCH_MERGE_STATEMENTS, self._statements),
            (queries.BATCH_MERGE_CONTROL_FLOWS, self._control_flows),
            (queries.BATCH_MERGE_BRANCHES, self._branches),
            (queries.BATCH_MERGE_CONTAINS, self._contains),
            (queries.BATCH_MERGE_NEXT, self._next),
            (queries.BATCH_MERGE_VARIABLES, self._variables),
            (queries.BATCH_MERGE_ASSIGNS, self._assigns),
            (queries.BATCH_MERGE_MUTATES, self._mutates),
            (queries.BATCH_MERGE_READS, self._reads),
            (queries.BATCH_MERGE_RETURNS, self._returns),
            (queries.BATCH_MERGE_PASSES_TO, self._passes_to),
            (queries.BATCH_MERGE_FEEDS, self._feeds),
        ]
        for query, items in batch_map:
            if items:
                self._graph.query(query, params={"items": items})
                count += 1
        logger.debug("BatchUpserter flushed %d queries", count)
        return count
