"""Logic Pack builders: pre-processed subgraphs for LLM consumption (TICKET-501)."""

from __future__ import annotations

import logging
from typing import Any

from app.graph.client import get_graph

logger = logging.getLogger(__name__)

# Type alias for Logic Pack structure
LogicPack = dict[str, Any]


def _node_to_dict(node) -> dict[str, str | int | bool | None]:  # type: ignore[no-untyped-def]
    """Convert a FalkorDB node to a dict."""
    labels = node.labels if hasattr(node, "labels") else []
    label = labels[0] if labels else "Unknown"
    props: dict[str, str | int | bool | None] = {}
    if hasattr(node, "properties"):
        for k, v in node.properties.items():
            if isinstance(v, (str, int, bool)) or v is None:
                props[k] = v
            else:
                props[k] = str(v)
    return {
        "id": props.get("name", ""),
        "label": label,
        "properties": props,
    }


def _edge_to_dict(
    edge_type: str, source: str, target: str, props: dict[str, Any] | None = None
) -> dict[str, str | int | bool | None]:
    """Build an edge dict."""
    sanitized: dict[str, str | int | bool | None] = {}
    if props:
        for k, v in props.items():
            if isinstance(v, (str, int, bool)) or v is None:
                sanitized[k] = v
            else:
                sanitized[k] = str(v)
    return {
        "type": edge_type,
        "source": source,
        "target": target,
        "properties": sanitized,
    }


def build_call_chain_pack(function_name: str, hops: int = 2) -> LogicPack:
    """Build a call chain Logic Pack: CALLS traversal from a function.

    Args:
        function_name: Qualified function name.
        hops: Maximum traversal depth.

    Returns:
        LogicPack with nodes, edges, and code snippets.
    """
    graph = get_graph()
    nodes_list: list[dict[str, Any]] = []
    edges_list: list[dict[str, Any]] = []
    snippets: dict[str, str] = {}
    seen_nodes: set[str] = set()

    # Get the center node
    center_result = graph.query(
        "MATCH (f:LogicNode) WHERE f.name CONTAINS $name AND f.status = 'active' RETURN f",
        params={"name": function_name},
    )
    if center_result.result_set:
        center = center_result.result_set[0][0]
        d = _node_to_dict(center)
        nodes_list.append(d)
        seen_nodes.add(str(d["id"]))
        source_text = center.properties.get("source_text", "") if hasattr(center, "properties") else ""
        if source_text:
            snippets[str(d["id"])] = source_text

    # Traverse CALLS edges
    call_result = graph.query(
        "MATCH path = (f:LogicNode)-[:CALLS*1.." + str(hops) + "]->(g:LogicNode) "
        "WHERE f.name CONTAINS $name AND f.status = 'active' "
        "RETURN nodes(path) AS ns, relationships(path) AS rs",
        params={"name": function_name},
    )
    for row in call_result.result_set:
        for node in row[0]:
            d = _node_to_dict(node)
            nid = str(d["id"])
            if nid not in seen_nodes:
                seen_nodes.add(nid)
                nodes_list.append(d)
                source_text = node.properties.get("source_text", "") if hasattr(node, "properties") else ""
                if source_text:
                    snippets[nid] = source_text
        for rel in row[1]:
            props = rel.properties if hasattr(rel, "properties") else {}
            edge_type = rel.relation if hasattr(rel, "relation") else "CALLS"
            src = props.get("source_name", "")
            tgt = props.get("target_name", "")
            # FalkorDB edges don't carry node names directly; use the path context
            edges_list.append(_edge_to_dict(str(edge_type), str(src), str(tgt), props))

    return {"nodes": nodes_list, "edges": edges_list, "snippets": snippets}


def build_mutation_timeline_pack(variable_name: str) -> LogicPack:
    """Build a mutation timeline Logic Pack for a variable.

    Args:
        variable_name: Qualified variable name.

    Returns:
        LogicPack with variable node, interacting functions, and all edges.
    """
    graph = get_graph()
    nodes_list: list[dict[str, Any]] = []
    edges_list: list[dict[str, Any]] = []
    snippets: dict[str, str] = {}
    seen_nodes: set[str] = set()

    # Get the variable
    var_result = graph.query(
        "MATCH (v:Variable {name: $name}) RETURN v",
        params={"name": variable_name},
    )
    if var_result.result_set:
        d = _node_to_dict(var_result.result_set[0][0])
        nodes_list.append(d)
        seen_nodes.add(str(d["id"]))

    # Get all interacting functions and edges
    for edge_type in ("ASSIGNS", "MUTATES", "READS", "RETURNS"):
        result = graph.query(
            f"MATCH (f:LogicNode)-[r:{edge_type}]->(v:Variable {{name: $name}}) RETURN f, r",
            params={"name": variable_name},
        )
        for row in result.result_set:
            func_node = row[0]
            edge = row[1]
            fd = _node_to_dict(func_node)
            fid = str(fd["id"])
            if fid not in seen_nodes:
                seen_nodes.add(fid)
                nodes_list.append(fd)
                st = func_node.properties.get("source_text", "") if hasattr(func_node, "properties") else ""
                if st:
                    snippets[fid] = st
            props = edge.properties if hasattr(edge, "properties") else {}
            edges_list.append(_edge_to_dict(edge_type, fid, variable_name, props))

    # PASSES_TO and FEEDS
    passes_result = graph.query(
        "MATCH (v:Variable {name: $name})-[p:PASSES_TO]->(t:Variable) RETURN t, p",
        params={"name": variable_name},
    )
    for row in passes_result.result_set:
        target = row[0]
        edge = row[1]
        td = _node_to_dict(target)
        tid = str(td["id"])
        if tid not in seen_nodes:
            seen_nodes.add(tid)
            nodes_list.append(td)
        props = edge.properties if hasattr(edge, "properties") else {}
        edges_list.append(_edge_to_dict("PASSES_TO", variable_name, tid, props))

    feeds_result = graph.query(
        "MATCH (src:Variable)-[fd:FEEDS]->(v:Variable {name: $name}) RETURN src, fd",
        params={"name": variable_name},
    )
    for row in feeds_result.result_set:
        source = row[0]
        edge = row[1]
        sd = _node_to_dict(source)
        sid = str(sd["id"])
        if sid not in seen_nodes:
            seen_nodes.add(sid)
            nodes_list.append(sd)
        props = edge.properties if hasattr(edge, "properties") else {}
        edges_list.append(_edge_to_dict("FEEDS", sid, variable_name, props))

    return {"nodes": nodes_list, "edges": edges_list, "snippets": snippets}


def build_impact_pack(function_name: str) -> LogicPack:
    """Build an impact analysis Logic Pack: variables a function mutates and their consumers.

    Args:
        function_name: Qualified function name.

    Returns:
        LogicPack with mutated variables and downstream consumers.
    """
    graph = get_graph()
    nodes_list: list[dict[str, Any]] = []
    edges_list: list[dict[str, Any]] = []
    snippets: dict[str, str] = {}
    seen_nodes: set[str] = set()

    # Center function
    center_result = graph.query(
        "MATCH (f:LogicNode) WHERE f.name CONTAINS $name AND f.status = 'active' RETURN f",
        params={"name": function_name},
    )
    if center_result.result_set:
        d = _node_to_dict(center_result.result_set[0][0])
        nodes_list.append(d)
        seen_nodes.add(str(d["id"]))
        st = center_result.result_set[0][0].properties.get("source_text", "")
        if st:
            snippets[str(d["id"])] = st

    # Mutated variables
    mutates_result = graph.query(
        "MATCH (f:LogicNode)-[m:MUTATES]->(v:Variable) WHERE f.name CONTAINS $name RETURN v, m",
        params={"name": function_name},
    )
    for row in mutates_result.result_set:
        var = row[0]
        edge = row[1]
        vd = _node_to_dict(var)
        vid = str(vd["id"])
        if vid not in seen_nodes:
            seen_nodes.add(vid)
            nodes_list.append(vd)
        props = edge.properties if hasattr(edge, "properties") else {}
        edges_list.append(_edge_to_dict("MUTATES", function_name, vid, props))

        # Downstream consumers
        consumers_result = graph.query(
            "MATCH (consumer:LogicNode)-[r:READS]->(v:Variable {name: $name}) RETURN consumer, r",
            params={"name": vid},
        )
        for crow in consumers_result.result_set:
            consumer = crow[0]
            cedge = crow[1]
            cd = _node_to_dict(consumer)
            cid = str(cd["id"])
            if cid not in seen_nodes:
                seen_nodes.add(cid)
                nodes_list.append(cd)
                cst = consumer.properties.get("source_text", "") if hasattr(consumer, "properties") else ""
                if cst:
                    snippets[cid] = cst
            cprops = cedge.properties if hasattr(cedge, "properties") else {}
            edges_list.append(_edge_to_dict("READS", cid, vid, cprops))

    return {"nodes": nodes_list, "edges": edges_list, "snippets": snippets}


def build_class_hierarchy_pack(class_name: str) -> LogicPack:
    """Build a class hierarchy Logic Pack: INHERITS tree with methods.

    Args:
        class_name: Qualified class name.

    Returns:
        LogicPack with class hierarchy and methods.
    """
    graph = get_graph()
    nodes_list: list[dict[str, Any]] = []
    edges_list: list[dict[str, Any]] = []
    snippets: dict[str, str] = {}
    seen_nodes: set[str] = set()

    # Traverse hierarchy
    hier_result = graph.query(
        "MATCH path = (c:LogicNode {kind: 'class'})-[:INHERITS*0..5]->(parent:LogicNode) "
        "WHERE c.name CONTAINS $name "
        "RETURN nodes(path) AS classes",
        params={"name": class_name},
    )
    for row in hier_result.result_set:
        prev_name: str | None = None
        for cls in row[0]:
            d = _node_to_dict(cls)
            cid = str(d["id"])
            if cid not in seen_nodes:
                seen_nodes.add(cid)
                nodes_list.append(d)
                st = cls.properties.get("source_text", "") if hasattr(cls, "properties") else ""
                if st:
                    snippets[cid] = st
            if prev_name is not None:
                edges_list.append(_edge_to_dict("INHERITS", prev_name, cid, {}))
            prev_name = cid

    # Methods of each class
    for node in list(nodes_list):
        nid = str(node["id"])
        methods_result = graph.query(
            "MATCH (m:LogicNode)-[:MEMBER_OF]->(c:LogicNode) WHERE c.name CONTAINS $name RETURN m",
            params={"name": nid},
        )
        for row in methods_result.result_set:
            method = row[0]
            md = _node_to_dict(method)
            mid = str(md["id"])
            if mid not in seen_nodes:
                seen_nodes.add(mid)
                nodes_list.append(md)
                st = method.properties.get("source_text", "") if hasattr(method, "properties") else ""
                if st:
                    snippets[mid] = st
            edges_list.append(_edge_to_dict("DEFINES", nid, mid, {}))

    return {"nodes": nodes_list, "edges": edges_list, "snippets": snippets}


def build_function_flow_pack(function_name: str) -> LogicPack:
    """Build a function flow Logic Pack: full Statement/ControlFlow/Branch subgraph.

    Args:
        function_name: Qualified function name.

    Returns:
        LogicPack with statement-level nodes and edges.
    """
    graph = get_graph()
    nodes_list: list[dict[str, Any]] = []
    edges_list: list[dict[str, Any]] = []
    snippets: dict[str, str] = {}
    seen_nodes: set[str] = set()

    # Center function
    center_result = graph.query(
        "MATCH (f:LogicNode) WHERE f.name CONTAINS $name AND f.status = 'active' RETURN f",
        params={"name": function_name},
    )
    if center_result.result_set:
        d = _node_to_dict(center_result.result_set[0][0])
        nodes_list.append(d)
        seen_nodes.add(str(d["id"]))
        st = center_result.result_set[0][0].properties.get("source_text", "")
        if st:
            snippets[str(d["id"])] = st

    # CONTAINS children (recursive up to 8 levels)
    contains_result = graph.query(
        "MATCH (f:LogicNode)-[:CONTAINS*1..8]->(child) WHERE f.name CONTAINS $name RETURN child",
        params={"name": function_name},
    )
    for row in contains_result.result_set:
        child = row[0]
        d = _node_to_dict(child)
        cid = str(d["id"])
        if cid not in seen_nodes:
            seen_nodes.add(cid)
            nodes_list.append(d)
            st = child.properties.get("source_text", "") if hasattr(child, "properties") else ""
            if st:
                snippets[cid] = st

    # CONTAINS edges
    contains_edges = graph.query(
        "MATCH (parent)-[r:CONTAINS]->(child) "
        "WHERE parent.name = $name OR parent.name STARTS WITH $prefix "
        "RETURN parent.name, child.name",
        params={"name": function_name, "prefix": function_name + "."},
    )
    for row in contains_edges.result_set:
        edges_list.append(_edge_to_dict("CONTAINS", row[0], row[1], {}))

    # NEXT edges
    next_edges = graph.query(
        "MATCH (a)-[r:NEXT]->(b) "
        "WHERE a.name STARTS WITH $prefix "
        "RETURN a.name, b.name",
        params={"prefix": function_name + "."},
    )
    for row in next_edges.result_set:
        edges_list.append(_edge_to_dict("NEXT", row[0], row[1], {}))

    # Variable nodes for this function
    var_result = graph.query(
        "MATCH (f:LogicNode)-[:ASSIGNS|READS|MUTATES|RETURNS]->(v:Variable) "
        "WHERE f.name CONTAINS $name RETURN v",
        params={"name": function_name},
    )
    for row in var_result.result_set:
        var = row[0]
        d = _node_to_dict(var)
        vid = str(d["id"])
        if vid not in seen_nodes:
            seen_nodes.add(vid)
            nodes_list.append(d)

    return {"nodes": nodes_list, "edges": edges_list, "snippets": snippets}
