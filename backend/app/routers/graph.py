"""Router for graph query endpoints."""

from __future__ import annotations

import logging

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException

from app.graph.client import get_graph
from app.models.exceptions import GraphQueryError, NodeNotFoundError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1", tags=["graph"])


class GraphNodeResponse(BaseModel):
    """A single graph node."""

    id: str
    label: str
    properties: dict[str, str | int | bool | None]


class GraphEdgeResponse(BaseModel):
    """A single graph edge."""

    type: str
    source: str
    target: str
    properties: dict[str, str | int | bool | None]


class GraphQueryRequest(BaseModel):
    """Request body for raw Cypher queries."""

    cypher: str


class GraphQueryResponse(BaseModel):
    """Response from a Cypher query."""

    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]
    raw_results: list[list[str | int | None]]


def _node_to_response(node) -> GraphNodeResponse:  # type: ignore[no-untyped-def]
    """Convert a FalkorDB node to a response model."""
    labels = node.labels if hasattr(node, "labels") else []
    label = labels[0] if labels else "Unknown"
    props: dict[str, str | int | bool | None] = {}
    if hasattr(node, "properties"):
        for k, v in node.properties.items():
            if isinstance(v, (str, int, bool)) or v is None:
                props[k] = v
            else:
                props[k] = str(v)
    node_id = props.get("name", str(node.id if hasattr(node, "id") else ""))
    return GraphNodeResponse(id=str(node_id), label=label, properties=props)


@router.get("/graph/nodes", response_model=list[GraphNodeResponse])
async def get_all_nodes(
    label: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[GraphNodeResponse]:
    """Get all nodes, optionally filtered by label."""
    try:
        graph = get_graph()
        if label:
            cypher = f"MATCH (n:{label}) RETURN n SKIP $offset LIMIT $limit"
        else:
            cypher = "MATCH (n) RETURN n SKIP $offset LIMIT $limit"
        result = graph.query(cypher, params={"offset": offset, "limit": limit})
        nodes: list[GraphNodeResponse] = []
        for row in result.result_set:
            node = row[0]
            nodes.append(_node_to_response(node))
        return nodes
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {exc}") from exc


class ModuleGraphResponse(BaseModel):
    """Response for the module dependency graph."""

    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]


class SubgraphResponse(BaseModel):
    """Generic response containing nodes and edges for any sub-graph view."""

    nodes: list[GraphNodeResponse]
    edges: list[GraphEdgeResponse]


def _extract_edge(rel, src_node, dst_node) -> GraphEdgeResponse:  # type: ignore[no-untyped-def]
    """Extract an edge response from a FalkorDB relationship and its endpoint nodes."""
    src_name = src_node.properties.get("name", str(src_node.id)) if hasattr(src_node, "properties") else ""
    dst_name = dst_node.properties.get("name", str(dst_node.id)) if hasattr(dst_node, "properties") else ""
    edge_type = rel.relation if hasattr(rel, "relation") and isinstance(rel.relation, str) else str(getattr(rel, "relation", ""))
    props: dict[str, str | int | bool | None] = {}
    if hasattr(rel, "properties"):
        for k, v in rel.properties.items():
            if isinstance(v, (str, int, bool)) or v is None:
                props[k] = v
            else:
                props[k] = str(v)
    return GraphEdgeResponse(type=edge_type, source=str(src_name), target=str(dst_name), properties=props)


@router.get("/graph/modules", response_model=ModuleGraphResponse)
async def get_module_graph() -> ModuleGraphResponse:
    """Get all Module nodes and IMPORTS edges between them."""
    try:
        graph = get_graph()
        # Fetch all Module nodes
        node_result = graph.query("MATCH (m:Module) RETURN m")
        nodes: list[GraphNodeResponse] = []
        for row in node_result.result_set:
            nodes.append(_node_to_response(row[0]))

        # Fetch IMPORTS edges between modules
        edge_result = graph.query("MATCH (m:Module)-[r:IMPORTS]->(n:Module) RETURN m, r, n")
        edges: list[GraphEdgeResponse] = []
        for row in edge_result.result_set:
            edges.append(_extract_edge(row[1], row[0], row[2]))

        return ModuleGraphResponse(nodes=nodes, edges=edges)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {exc}") from exc


@router.get("/graph/file-members/{module_path:path}", response_model=SubgraphResponse)
async def get_file_members(module_path: str) -> SubgraphResponse:
    """Get the direct members (Classes, Functions) of a file.

    Returns only the Module node's direct DEFINES children and
    INHERITS edges between classes within the file. This is the
    top-level structure of a single file.

    Args:
        module_path: The module's file path (e.g. ``app/services/ast_parser.py``).
    """
    try:
        graph = get_graph()

        # Get direct DEFINES children of the module node
        result = graph.query(
            "MATCH (m:Module {module_path: $mp})-[:DEFINES]->(n) RETURN n",
            params={"mp": module_path},
        )
        nodes: list[GraphNodeResponse] = []
        seen: set[str] = set()
        for row in result.result_set:
            resp = _node_to_response(row[0])
            if resp.id not in seen:
                seen.add(resp.id)
                nodes.append(resp)

        # Get INHERITS and CALLS edges between these direct members
        edges: list[GraphEdgeResponse] = []
        if seen:
            edge_result = graph.query(
                "MATCH (m:Module {module_path: $mp})-[:DEFINES]->(a)"
                "-[r:INHERITS|CALLS]->"
                "(b)<-[:DEFINES]-(m2:Module {module_path: $mp}) "
                "RETURN a, r, b",
                params={"mp": module_path},
            )
            for row in edge_result.result_set:
                edges.append(_extract_edge(row[1], row[0], row[2]))

        return SubgraphResponse(nodes=nodes, edges=edges)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {exc}") from exc


@router.get("/graph/class/{class_name:path}", response_model=SubgraphResponse)
async def get_class_detail(class_name: str) -> SubgraphResponse:
    """Get a class's methods, base classes, and inter-method calls.

    Returns the Class node, its DEFINES children (methods), INHERITS
    edges to base classes, and CALLS edges between methods within the class.

    Args:
        class_name: Fully qualified class name (e.g. ``calculator.Calculator``).
    """
    try:
        graph = get_graph()
        nodes: list[GraphNodeResponse] = []
        edges: list[GraphEdgeResponse] = []
        seen: set[str] = set()

        # The class node itself
        cls_result = graph.query(
            "MATCH (c:Class {name: $name}) RETURN c LIMIT 1",
            params={"name": class_name},
        )
        if cls_result.result_set:
            resp = _node_to_response(cls_result.result_set[0][0])
            seen.add(resp.id)
            nodes.append(resp)

        # Methods defined by the class
        methods_result = graph.query(
            "MATCH (c:Class {name: $name})-[r:DEFINES]->(m:Function) RETURN c, r, m",
            params={"name": class_name},
        )
        for row in methods_result.result_set:
            method_resp = _node_to_response(row[2])
            if method_resp.id not in seen:
                seen.add(method_resp.id)
                nodes.append(method_resp)
            edges.append(_extract_edge(row[1], row[0], row[2]))

        # Base classes (INHERITS edges)
        inherits_result = graph.query(
            "MATCH (c:Class {name: $name})-[r:INHERITS]->(base) RETURN c, r, base",
            params={"name": class_name},
        )
        for row in inherits_result.result_set:
            base_resp = _node_to_response(row[2])
            if base_resp.id not in seen:
                seen.add(base_resp.id)
                base_resp.properties["external"] = True
                nodes.append(base_resp)
            edges.append(_extract_edge(row[1], row[0], row[2]))

        # Inter-method CALLS within the class
        calls_result = graph.query(
            "MATCH (c:Class {name: $name})-[:DEFINES]->(a:Function)-[r:CALLS]->(b:Function)<-[:DEFINES]-(c) "
            "RETURN a, r, b",
            params={"name": class_name},
        )
        for row in calls_result.result_set:
            edges.append(_extract_edge(row[1], row[0], row[2]))

        return SubgraphResponse(nodes=nodes, edges=edges)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {exc}") from exc


@router.get("/graph/function/{function_name:path}", response_model=SubgraphResponse)
async def get_function_detail(
    function_name: str,
    include_flow: bool = False,
) -> SubgraphResponse:
    """Get what a function calls and its variables.

    Returns the function's CALLS targets, DEFINES children (nested functions),
    and connected Variable nodes with their edges (ASSIGNS, READS, MUTATES,
    PASSES_TO, RETURNS, FEEDS).

    When ``include_flow`` is true, also returns the internal control flow graph:
    Statement, ControlFlow, and Branch child nodes with CONTAINS, NEXT, and
    statement-level CALLS edges.

    Args:
        function_name: Fully qualified function name (e.g. ``calculator.Calculator.add``).
        include_flow: If true, include internal control flow nodes and edges.
    """
    try:
        graph = get_graph()
        nodes: list[GraphNodeResponse] = []
        edges: list[GraphEdgeResponse] = []
        seen: set[str] = set()

        # The function node itself
        fn_result = graph.query(
            "MATCH (f {name: $name}) WHERE f:Function OR f:Class RETURN f LIMIT 1",
            params={"name": function_name},
        )
        if fn_result.result_set:
            resp = _node_to_response(fn_result.result_set[0][0])
            seen.add(resp.id)
            nodes.append(resp)

        if include_flow:
            # --- Control flow mode ---

            # 1. All internal children (Statement, ControlFlow, Branch) up to 8 hops
            #    (supports deeply nested control flow, e.g. try inside try inside for)
            child_result = graph.query(
                "MATCH (f {name: $name})-[:CONTAINS*1..8]->(child) "
                "WHERE child:Statement OR child:ControlFlow OR child:Branch "
                "RETURN child",
                params={"name": function_name},
            )
            for row in child_result.result_set:
                child_resp = _node_to_response(row[0])
                if child_resp.id not in seen:
                    seen.add(child_resp.id)
                    nodes.append(child_resp)

            # 2. CONTAINS edges (structural hierarchy)
            contains_result = graph.query(
                "MATCH (f {name: $name})-[:CONTAINS*0..7]->(parent)-[r:CONTAINS]->(child) "
                "WHERE (parent:Function OR parent:ControlFlow OR parent:Branch) "
                "AND (child:Statement OR child:ControlFlow OR child:Branch) "
                "RETURN parent, r, child",
                params={"name": function_name},
            )
            for row in contains_result.result_set:
                edges.append(_extract_edge(row[1], row[0], row[2]))

            # 3. NEXT edges (sequential ordering)
            next_result = graph.query(
                "MATCH (f {name: $name})-[:CONTAINS*1..8]->(a)-[r:NEXT]->(b) "
                "RETURN a, r, b",
                params={"name": function_name},
            )
            for row in next_result.result_set:
                edge_resp = _extract_edge(row[1], row[0], row[2])
                src_labels = row[0].labels if hasattr(row[0], "labels") else []
                dst_labels = row[2].labels if hasattr(row[2], "labels") else []
                if "ControlFlow" in src_labels and "Branch" in dst_labels:
                    dst_kind = row[2].properties.get("kind", "") if hasattr(row[2], "properties") else ""
                    edge_resp.properties["branch_kind"] = dst_kind
                edges.append(edge_resp)

            # 4. Statement-level CALLS: link statements to the external functions they call
            calls_result = graph.query(
                "MATCH (f {name: $name})-[c:CALLS]->(callee) "
                "MATCH (f)-[:CONTAINS*1..8]->(s) "
                "WHERE (s:Statement OR s:ControlFlow) "
                "AND c.call_line >= s.start_line AND c.call_line <= s.end_line "
                "RETURN s, c, callee",
                params={"name": function_name},
            )
            for row in calls_result.result_set:
                callee_resp = _node_to_response(row[2])
                if callee_resp.id not in seen:
                    seen.add(callee_resp.id)
                    callee_resp.properties["external"] = True
                    nodes.append(callee_resp)
                edges.append(_extract_edge(row[1], row[0], row[2]))

        else:
            # --- Semantic mode (original behaviour) ---

            # Outgoing edges: CALLS, DEFINES, ASSIGNS, MUTATES, READS, PASSES_TO, RETURNS, FEEDS
            out_result = graph.query(
                "MATCH (f {name: $name})-[r]->(n) RETURN f, r, n",
                params={"name": function_name},
            )
            for row in out_result.result_set:
                target_resp = _node_to_response(row[2])
                if target_resp.id not in seen:
                    seen.add(target_resp.id)
                    # Mark external call targets
                    target_mp = row[2].properties.get("module_path", "") if hasattr(row[2], "properties") else ""
                    fn_mp = row[0].properties.get("module_path", "") if hasattr(row[0], "properties") else ""
                    if target_mp and fn_mp and target_mp != fn_mp:
                        target_resp.properties["external"] = True
                    nodes.append(target_resp)
                edges.append(_extract_edge(row[1], row[0], row[2]))

            # Incoming edges to the function (e.g. other functions calling it)
            in_result = graph.query(
                "MATCH (f {name: $name})<-[r]-(n) RETURN n, r, f",
                params={"name": function_name},
            )
            for row in in_result.result_set:
                src_resp = _node_to_response(row[0])
                if src_resp.id not in seen:
                    seen.add(src_resp.id)
                    src_resp.properties["external"] = True
                    nodes.append(src_resp)
                edges.append(_extract_edge(row[1], row[0], row[2]))

        return SubgraphResponse(nodes=nodes, edges=edges)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {exc}") from exc


@router.get("/graph/variable/{variable_name:path}", response_model=SubgraphResponse)
async def get_variable_detail(variable_name: str) -> SubgraphResponse:
    """Get how a variable flows through the code.

    Returns the variable node and all connected nodes/edges showing
    assignments, reads, mutations, passes, returns, and feeds.

    Args:
        variable_name: Fully qualified variable name.
    """
    try:
        graph = get_graph()
        nodes: list[GraphNodeResponse] = []
        edges: list[GraphEdgeResponse] = []
        seen: set[str] = set()

        # The variable node itself
        var_result = graph.query(
            "MATCH (v:Variable {name: $name}) RETURN v LIMIT 1",
            params={"name": variable_name},
        )
        if var_result.result_set:
            resp = _node_to_response(var_result.result_set[0][0])
            seen.add(resp.id)
            nodes.append(resp)

        # All edges connected to this variable (both directions)
        out_result = graph.query(
            "MATCH (v:Variable {name: $name})-[r]->(n) RETURN v, r, n",
            params={"name": variable_name},
        )
        for row in out_result.result_set:
            target_resp = _node_to_response(row[2])
            if target_resp.id not in seen:
                seen.add(target_resp.id)
                nodes.append(target_resp)
            edges.append(_extract_edge(row[1], row[0], row[2]))

        in_result = graph.query(
            "MATCH (v:Variable {name: $name})<-[r]-(n) RETURN n, r, v",
            params={"name": variable_name},
        )
        for row in in_result.result_set:
            src_resp = _node_to_response(row[0])
            if src_resp.id not in seen:
                seen.add(src_resp.id)
                nodes.append(src_resp)
            edges.append(_extract_edge(row[1], row[0], row[2]))

        return SubgraphResponse(nodes=nodes, edges=edges)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {exc}") from exc


@router.get("/graph/node/{node_id}", response_model=GraphNodeResponse)
async def get_node(node_id: str) -> GraphNodeResponse:
    """Get a single node by name."""
    try:
        graph = get_graph()
        result = graph.query(
            "MATCH (n) WHERE n.name = $name RETURN n LIMIT 1",
            params={"name": node_id},
        )
        if not result.result_set:
            raise NodeNotFoundError(node_id)
        node = result.result_set[0][0]
        return _node_to_response(node)
    except NodeNotFoundError:
        raise HTTPException(status_code=404, detail=f"Node not found: {node_id}") from None
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {exc}") from exc


@router.post("/graph/query-subgraph", response_model=SubgraphResponse)
async def query_subgraph(request: GraphQueryRequest) -> SubgraphResponse:
    """Execute a Cypher query and return a subgraph with edges between matched nodes.

    Collects node objects directly returned by the query, and also resolves any
    scalar string values as potential node names. Then fetches all edges between
    the collected nodes so the result renders as a connected graph.

    Args:
        request: Cypher query to execute.
    """
    try:
        graph = get_graph()
        result = graph.query(request.cypher)

        nodes: list[GraphNodeResponse] = []
        seen: set[str] = set()
        # Collect scalar strings that might be node names
        candidate_names: set[str] = set()

        for row in result.result_set:
            for item in row:
                if hasattr(item, "labels"):
                    resp = _node_to_response(item)
                    if resp.id not in seen:
                        seen.add(resp.id)
                        nodes.append(resp)
                elif isinstance(item, str) and item:
                    candidate_names.add(item)

        # Resolve scalar strings to full nodes (handles RETURN f.name, n.name, etc.)
        unresolved = candidate_names - seen
        if unresolved:
            name_list = list(unresolved)
            resolve_result = graph.query(
                "MATCH (n) WHERE n.name IN $names RETURN n",
                params={"names": name_list},
            )
            for row in resolve_result.result_set:
                resp = _node_to_response(row[0])
                if resp.id not in seen:
                    seen.add(resp.id)
                    nodes.append(resp)

        # Fetch edges between the collected nodes (and outgoing edges for single-node results)
        edges: list[GraphEdgeResponse] = []
        if seen:
            name_list = list(seen)
            edge_result = graph.query(
                "MATCH (a)-[r]->(b) "
                "WHERE a.name IN $names AND b.name IN $names "
                "RETURN a, r, b",
                params={"names": name_list},
            )
            for row in edge_result.result_set:
                edges.append(_extract_edge(row[1], row[0], row[2]))

        return SubgraphResponse(nodes=nodes, edges=edges)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Graph query failed: {exc}") from exc


@router.post("/query", response_model=GraphQueryResponse)
async def execute_query(request: GraphQueryRequest) -> GraphQueryResponse:
    """Execute a raw Cypher query against the graph."""
    try:
        graph = get_graph()
        result = graph.query(request.cypher)
        nodes: list[GraphNodeResponse] = []
        edges: list[GraphEdgeResponse] = []
        raw_results: list[list[str | int | None]] = []

        for row in result.result_set:
            raw_row: list[str | int | None] = []
            for item in row:
                if hasattr(item, "labels"):
                    nodes.append(_node_to_response(item))
                    raw_row.append(str(item.properties.get("name", "")))
                elif hasattr(item, "relation"):
                    edge_type = item.relation if isinstance(item.relation, str) else str(item.relation)
                    props: dict[str, str | int | bool | None] = {}
                    if hasattr(item, "properties"):
                        for k, v in item.properties.items():
                            if isinstance(v, (str, int, bool)) or v is None:
                                props[k] = v
                            else:
                                props[k] = str(v)
                    edges.append(GraphEdgeResponse(
                        type=edge_type,
                        source=str(item.src_node) if hasattr(item, "src_node") else "",
                        target=str(item.dest_node) if hasattr(item, "dest_node") else "",
                        properties=props,
                    ))
                    raw_row.append(edge_type)
                elif isinstance(item, (str, int)):
                    raw_row.append(item)
                elif item is None:
                    raw_row.append(None)
                else:
                    raw_row.append(str(item))
            raw_results.append(raw_row)

        return GraphQueryResponse(nodes=nodes, edges=edges, raw_results=raw_results)
    except Exception as exc:
        raise GraphQueryError(str(exc)) from exc
