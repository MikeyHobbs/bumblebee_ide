"""Logic Node CRUD service (TICKET-810).

Create, read, update, deprecate operations for LogicNodes with automatic
Variable extraction on create/update.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from app.graph.client import get_graph
from app.graph import logic_queries as lq
from app.models.exceptions import NodeNotFoundError
from app.models.logic_models import (
    EdgeType,
    LogicNodeCreate,
    LogicNodeKind,
    LogicNodeResponse,
    LogicNodeUpdate,
    NodeStatus,
    ParamKind,
    ParamSpec,
    VariableResponse,
)
from app.services.analysis.hash_identity import (
    compute_ast_hash,
    detect_signature_change,
    extract_params_detailed,
    extract_return_type,
    extract_signature_text,
    generate_node_id,
)
from app.services.codegen.write_back import append_function_to_file, replace_function_in_file
from app.config import settings

import logging

logger = logging.getLogger(__name__)


def _node_from_graph(record: Any) -> LogicNodeResponse:
    """Convert a FalkorDB node record to a LogicNodeResponse.

    Args:
        record: A FalkorDB node result.

    Returns:
        Populated LogicNodeResponse.
    """
    props = record.properties if hasattr(record, "properties") else record

    # Parse params from JSON string if stored that way
    raw_params = props.get("params", [])
    if isinstance(raw_params, str):
        raw_params = json.loads(raw_params) if raw_params else []

    params = []
    for p in raw_params:
        if isinstance(p, dict):
            params.append(ParamSpec(
                name=p.get("name", ""),
                type_hint=p.get("type_hint"),
                default=p.get("default"),
                kind=ParamKind(p.get("kind", "positional_or_keyword")),
            ))

    # Parse list fields
    decorators = props.get("decorators", [])
    if isinstance(decorators, str):
        decorators = json.loads(decorators) if decorators else []
    tags = props.get("tags", [])
    if isinstance(tags, str):
        tags = json.loads(tags) if tags else []

    return LogicNodeResponse(
        id=props.get("id", ""),
        ast_hash=props.get("ast_hash", ""),
        kind=LogicNodeKind(props.get("kind", "function")),
        name=props.get("name", ""),
        module_path=props.get("module_path", ""),
        signature=props.get("signature", ""),
        source_text=props.get("source_text", ""),
        semantic_intent=props.get("semantic_intent"),
        docstring=props.get("docstring"),
        decorators=decorators,
        params=params,
        return_type=props.get("return_type"),
        tags=tags,
        class_id=props.get("class_id"),
        derived_from=props.get("derived_from"),
        start_line=props.get("start_line"),
        end_line=props.get("end_line"),
        status=NodeStatus(props.get("status", "active")),
        created_at=_parse_datetime(props.get("created_at", "")),
        updated_at=_parse_datetime(props.get("updated_at", "")),
    )


def _parse_datetime(value: Any) -> datetime:
    """Parse a datetime from various formats."""
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        # Handle ISO 8601
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    return datetime.now(timezone.utc)


def ensure_indexes() -> None:
    """Create all required indexes if they don't exist."""
    graph = get_graph()
    for stmt in lq.INDEX_STATEMENTS:
        try:
            graph.query(stmt)
        except Exception:  # pylint: disable=broad-except  # Index may already exist
            pass


def create_node(data: LogicNodeCreate) -> LogicNodeResponse:
    """Create a new LogicNode in the graph.

    Generates UUID7, computes AST hash, checks for duplicates, writes to
    FalkorDB, and auto-extracts Variable nodes + edges.

    Args:
        data: The LogicNode creation parameters.

    Returns:
        The created LogicNodeResponse with computed fields and any warnings.
    """
    graph = get_graph()
    now = datetime.now(timezone.utc).isoformat()

    node_id = generate_node_id()
    ast_hash = compute_ast_hash(data.source_text)
    signature = extract_signature_text(data.source_text)
    return_type = extract_return_type(data.source_text)
    params_raw = extract_params_detailed(data.source_text)

    # Determine kind for methods
    kind = data.kind.value

    warnings: list[str] = []

    # Check for duplicates
    try:
        dup_result = graph.query(
            lq.CHECK_DUPLICATE,
            params={"ast_hash": ast_hash, "current_id": node_id},
        )
        if dup_result.result_set:
            for row in dup_result.result_set:
                dup_name = row[1] if len(row) > 1 else "unknown"
                dup_id = row[0] if row else "unknown"
                warnings.append(f"Duplicate logic detected: existing node '{dup_name}' ({dup_id}) has identical AST")
    except Exception:  # pylint: disable=broad-except  # Graph may be empty
        pass

    # Serialize params as JSON string for graph storage
    params_json = json.dumps(params_raw)
    decorators_json = json.dumps(data.decorators)
    tags_json = json.dumps(data.tags)

    graph.query(
        lq.MERGE_LOGIC_NODE,
        params={
            "id": node_id,
            "ast_hash": ast_hash,
            "kind": kind,
            "name": data.name,
            "module_path": data.module_path,
            "signature": signature,
            "source_text": data.source_text,
            "semantic_intent": data.semantic_intent or "",
            "docstring": data.docstring or "",
            "decorators": decorators_json,
            "params": params_json,
            "return_type": return_type or "",
            "tags": tags_json,
            "class_id": data.class_id or "",
            "derived_from": data.derived_from or "",
            "start_line": 0,
            "end_line": 0,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
    )

    # Create MEMBER_OF edge if method with class_id
    if data.class_id and kind in ("method", "function"):
        try:
            graph.query(
                lq.EDGE_MERGE_QUERIES["MEMBER_OF"],
                params={
                    "source_id": node_id,
                    "target_id": data.class_id,
                    "properties": {"access": "public"},
                },
            )
        except Exception:  # pylint: disable=broad-except  # Class may not exist yet
            warnings.append(f"Could not create MEMBER_OF edge to class {data.class_id}")

    # Auto-extract variables
    _extract_variables_for_node(node_id, data.name, data.source_text, data.module_path)

    # Write-back: append the new function to the source file on disk
    if data.module_path:
        try:
            append_function_to_file(data.source_text, data.module_path, settings.watch_path or "")
        except Exception:  # pylint: disable=broad-except  # Write-back is best-effort
            logger.warning("Write-back failed for new node %s in %s", node_id, data.module_path, exc_info=True)

    response = get_node(node_id)
    response.warnings = warnings
    return response


def get_node(node_id: str) -> LogicNodeResponse:
    """Fetch a LogicNode by UUID.

    Args:
        node_id: The UUID of the LogicNode.

    Returns:
        LogicNodeResponse.

    Raises:
        NodeNotFoundError: If no node with the given ID exists.
    """
    graph = get_graph()
    result = graph.query(lq.GET_LOGIC_NODE_BY_ID, params={"id": node_id})

    if not result.result_set:
        raise NodeNotFoundError(node_id)

    return _node_from_graph(result.result_set[0][0])


def find_nodes(
    query: str = "",
    kind: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[LogicNodeResponse]:
    """Search for LogicNodes by name, semantic intent, or kind.

    Args:
        query: Search string matched against name and semantic_intent.
        kind: Filter by LogicNodeKind value.
        limit: Max results.
        offset: Pagination offset.

    Returns:
        List of matching LogicNodeResponse objects.
    """
    graph = get_graph()
    result = graph.query(
        lq.FIND_LOGIC_NODES,
        params={
            "query": query or "",
            "kind": kind or "",
            "offset": offset,
            "limit": limit,
        },
    )

    return [_node_from_graph(row[0]) for row in result.result_set]


def update_node(node_id: str, data: LogicNodeUpdate) -> LogicNodeResponse:
    """Update a LogicNode in-place.

    Same UUID, new AST hash. Re-extracts Variable nodes and data-flow edges.

    Args:
        node_id: UUID of the LogicNode to update.
        data: Fields to update.

    Returns:
        Updated LogicNodeResponse with warnings if signature changed.

    Raises:
        NodeNotFoundError: If no node with the given ID exists.
    """
    existing = get_node(node_id)
    graph = get_graph()
    now = datetime.now(timezone.utc).isoformat()
    warnings: list[str] = []

    source_text = data.source_text if data.source_text is not None else existing.source_text
    semantic_intent = data.semantic_intent if data.semantic_intent is not None else existing.semantic_intent
    tags = data.tags if data.tags is not None else existing.tags
    docstring = data.docstring if data.docstring is not None else existing.docstring

    # Check signature change
    if data.source_text is not None and detect_signature_change(existing.source_text, data.source_text):
        warnings.append(
            "Signature changed — consider creating a new node instead of updating. "
            "Use create_node(derived_from=existing_id) to fork."
        )

    ast_hash = compute_ast_hash(source_text)
    signature = extract_signature_text(source_text)
    return_type = extract_return_type(source_text)
    params_raw = extract_params_detailed(source_text)

    params_json = json.dumps(params_raw)
    tags_json = json.dumps(tags)

    graph.query(
        lq.MERGE_LOGIC_NODE,
        params={
            "id": node_id,
            "ast_hash": ast_hash,
            "kind": existing.kind.value,
            "name": existing.name,
            "module_path": existing.module_path,
            "signature": signature,
            "source_text": source_text,
            "semantic_intent": semantic_intent or "",
            "docstring": docstring or "",
            "decorators": json.dumps(existing.decorators),
            "params": params_json,
            "return_type": return_type or "",
            "tags": tags_json,
            "class_id": existing.class_id or "",
            "derived_from": existing.derived_from or "",
            "start_line": existing.start_line or 0,
            "end_line": existing.end_line or 0,
            "status": existing.status.value,
            "created_at": existing.created_at.isoformat(),
            "updated_at": now,
        },
    )

    # Re-extract variables if source changed
    if data.source_text is not None:
        # Delete old variables for this node
        graph.query(lq.DELETE_VARIABLES_FOR_NODE, params={"node_id": node_id})
        _extract_variables_for_node(node_id, existing.name, source_text, existing.module_path)

    # Write-back: replace the function source in the file on disk
    if (
        data.source_text is not None
        and existing.module_path
        and existing.start_line
        and existing.end_line
    ):
        try:
            abs_path = os.path.join(
                os.path.abspath(settings.watch_path or ""), existing.module_path
            )
            replace_function_in_file(source_text, abs_path, existing.start_line, existing.end_line)
        except Exception:  # pylint: disable=broad-except  # Write-back is best-effort
            logger.warning(
                "Write-back failed for updated node %s in %s", node_id, existing.module_path, exc_info=True
            )

    response = get_node(node_id)
    response.warnings = warnings
    return response


def deprecate_node(node_id: str, replacement_id: str | None = None) -> None:
    """Soft-delete a LogicNode by setting status to 'deprecated'.

    Edges are preserved as historical record.

    Args:
        node_id: UUID of the LogicNode to deprecate.
        replacement_id: Optional UUID of the replacement node.

    Raises:
        NodeNotFoundError: If no node with the given ID exists.
    """
    # Verify exists
    get_node(node_id)

    graph = get_graph()
    now = datetime.now(timezone.utc).isoformat()

    graph.query(lq.DEPRECATE_LOGIC_NODE, params={"id": node_id, "updated_at": now})

    # Optionally link to replacement
    if replacement_id:
        try:
            graph.query(
                lq.EDGE_MERGE_QUERIES["DEPENDS_ON"],
                params={
                    "source_id": node_id,
                    "target_id": replacement_id,
                    "properties": {"kind": "replaced_by"},
                },
            )
        except Exception:  # pylint: disable=broad-except  # Replacement may not exist
            pass


def _extract_variables_for_node(
    node_id: str,
    node_name: str,
    source_text: str,
    module_path: str,
) -> list[VariableResponse]:
    """Auto-extract Variable nodes and edges from a LogicNode's source.

    Reuses the existing variable_extractor and dataflow_extractor modules.

    Args:
        node_id: UUID of the LogicNode.
        node_name: Qualified name of the LogicNode.
        source_text: The LogicNode's source code.
        module_path: Module path for scoping.

    Returns:
        List of created VariableResponse objects.
    """
    from app.services.parsing.ast_parser import ParsedNode  # pylint: disable=import-outside-toplevel
    from app.services.parsing.variable_extractor import extract_variables  # pylint: disable=import-outside-toplevel

    graph = get_graph()
    now = datetime.now(timezone.utc).isoformat()

    # Build a minimal ParsedNode for the variable extractor
    parsed_node = ParsedNode(
        node_type="Function",
        name=node_name,
        start_line=1,
        end_line=source_text.count("\n") + 1,
        start_col=0,
        end_col=0,
        source_text=source_text,
        module_path=module_path,
    )

    try:
        var_result = extract_variables(source_text, module_path, [parsed_node])
    except Exception:  # pylint: disable=broad-except  # Extraction may fail on partial code
        return []

    created_vars: list[VariableResponse] = []

    for var_node in var_result.nodes:
        var_id = generate_node_id()
        is_param = var_node.origin_line == 1 and "." not in var_node.name.split(".")[-1]
        is_attr = "self." in var_node.name

        graph.query(
            lq.MERGE_VARIABLE,
            params={
                "id": var_id,
                "name": var_node.name,
                "scope": var_node.scope,
                "origin_node_id": node_id,
                "origin_line": var_node.origin_line,
                "type_hint": var_node.type_hint or "",
                "is_parameter": is_param,
                "is_attribute": is_attr,
                "created_at": now,
            },
        )

        created_vars.append(VariableResponse(
            id=var_id,
            name=var_node.name,
            scope=var_node.scope,
            origin_node_id=node_id,
            origin_line=var_node.origin_line,
            type_hint=var_node.type_hint,
            is_parameter=is_param,
            is_attribute=is_attr,
            created_at=_parse_datetime(now),
        ))

    # Create edges from variable extractor results
    # Map variable names to their UUIDs
    var_name_to_id: dict[str, str] = {v.name: v.id for v in created_vars}

    for edge in var_result.edges:
        target_var_id = var_name_to_id.get(edge.target_name)
        if not target_var_id:
            continue

        edge_type = edge.edge_type
        if edge_type in ("ASSIGNS", "MUTATES", "READS", "RETURNS"):
            query_key = edge_type
            if query_key in lq.EDGE_MERGE_QUERIES:
                props = dict(edge.properties) if edge.properties else {}
                try:
                    graph.query(
                        lq.EDGE_MERGE_QUERIES[query_key],
                        params={
                            "source_id": node_id,
                            "target_id": target_var_id,
                            "properties": props,
                        },
                    )
                except Exception:  # pylint: disable=broad-except  # Edge creation may fail
                    pass

    return created_vars
