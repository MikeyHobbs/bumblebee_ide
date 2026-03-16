"""Cypher query templates for graph operations."""

from __future__ import annotations


# Node MERGE queries
MERGE_MODULE = """
MERGE (m:Module {name: $name})
SET m.start_line = $start_line,
    m.end_line = $end_line,
    m.module_path = $module_path,
    m.checksum = $checksum
RETURN m
"""

MERGE_CLASS = """
MERGE (c:Class {name: $name})
SET c.start_line = $start_line,
    c.end_line = $end_line,
    c.start_col = $start_col,
    c.end_col = $end_col,
    c.source_text = $source_text,
    c.module_path = $module_path,
    c.decorators = $decorators,
    c.docstring = $docstring
RETURN c
"""

MERGE_FUNCTION = """
MERGE (f:Function {name: $name})
SET f.start_line = $start_line,
    f.end_line = $end_line,
    f.start_col = $start_col,
    f.end_col = $end_col,
    f.source_text = $source_text,
    f.module_path = $module_path,
    f.params = $params,
    f.decorators = $decorators,
    f.docstring = $docstring,
    f.is_async = $is_async
RETURN f
"""

# Edge MERGE queries
MERGE_DEFINES = """
MATCH (parent {name: $source_name})
MATCH (child {name: $target_name})
MERGE (parent)-[r:DEFINES]->(child)
RETURN r
"""

# Deletion queries for re-indexing
DELETE_MODULE_NODES = """
MATCH (n)
WHERE n.module_path = $module_path
DETACH DELETE n
"""

# Query for checking module checksum
GET_MODULE_CHECKSUM = """
MATCH (m:Module {module_path: $module_path})
RETURN m.checksum AS checksum
"""

# Query all nodes
GET_ALL_NODES = """
MATCH (n)
RETURN n
"""

GET_NODE_BY_ID = """
MATCH (n)
WHERE ID(n) = $node_id
RETURN n
"""

# Relationship edge MERGE queries (TICKET-103)
MERGE_CALLS = """
MATCH (caller:Function {name: $source_name})
MATCH (callee {name: $target_name})
MERGE (caller)-[r:CALLS {call_line: $call_line}]->(callee)
SET r.seq = $seq,
    r.call_order = $call_order
RETURN r
"""

MERGE_INHERITS = """
MATCH (child:Class {name: $source_name})
MATCH (parent:Class {name: $target_name})
MERGE (child)-[r:INHERITS]->(parent)
RETURN r
"""

MERGE_IMPORTS = """
MATCH (importer:Module {name: $source_name})
MATCH (imported:Module {name: $target_name})
MERGE (importer)-[r:IMPORTS]->(imported)
SET r.alias = $alias
RETURN r
"""

# Statement/ControlFlow/Branch node MERGE queries (TICKET-104)
MERGE_STATEMENT = """
MERGE (s:Statement {name: $name})
SET s.kind = $kind,
    s.source_text = $source_text,
    s.start_line = $start_line,
    s.end_line = $end_line,
    s.start_col = $start_col,
    s.end_col = $end_col,
    s.seq = $seq,
    s.module_path = $module_path
RETURN s
"""

MERGE_CONTROL_FLOW = """
MERGE (cf:ControlFlow {name: $name})
SET cf.kind = $kind,
    cf.condition_text = $condition_text,
    cf.source_text = $source_text,
    cf.start_line = $start_line,
    cf.end_line = $end_line,
    cf.start_col = $start_col,
    cf.end_col = $end_col,
    cf.seq = $seq,
    cf.module_path = $module_path
RETURN cf
"""

MERGE_BRANCH = """
MERGE (b:Branch {name: $name})
SET b.kind = $kind,
    b.condition_text = $condition_text,
    b.source_text = $source_text,
    b.start_line = $start_line,
    b.end_line = $end_line,
    b.start_col = $start_col,
    b.end_col = $end_col,
    b.seq = $seq,
    b.module_path = $module_path
RETURN b
"""

MERGE_CONTAINS = """
MATCH (parent {name: $source_name})
MATCH (child {name: $target_name})
MERGE (parent)-[r:CONTAINS]->(child)
RETURN r
"""

MERGE_NEXT = """
MATCH (prev {name: $source_name})
MATCH (next {name: $target_name})
MERGE (prev)-[r:NEXT]->(next)
RETURN r
"""

# Variable node MERGE queries (TICKET-201/202)
MERGE_VARIABLE = """
MERGE (v:Variable {name: $name})
SET v.scope = $scope,
    v.origin_line = $origin_line,
    v.origin_func = $origin_func,
    v.type_hint = $type_hint,
    v.module_path = $module_path
RETURN v
"""

MERGE_ASSIGNS = """
MATCH (f:Function {name: $source_name})
MATCH (v:Variable {name: $target_name})
MERGE (f)-[r:ASSIGNS {line: $line, seq: $seq}]->(v)
SET r.col = $col,
    r.is_rebind = $is_rebind,
    r.control_context = $control_context,
    r.branch = $branch
RETURN r
"""

MERGE_MUTATES = """
MATCH (f:Function {name: $source_name})
MATCH (v:Variable {name: $target_name})
MERGE (f)-[r:MUTATES {line: $line, seq: $seq}]->(v)
SET r.mutation_kind = $mutation_kind,
    r.control_context = $control_context,
    r.branch = $branch
RETURN r
"""

MERGE_READS = """
MATCH (f:Function {name: $source_name})
MATCH (v:Variable {name: $target_name})
MERGE (f)-[r:READS {line: $line, seq: $seq}]->(v)
SET r.control_context = $control_context,
    r.branch = $branch
RETURN r
"""

MERGE_RETURNS = """
MATCH (f:Function {name: $source_name})
MATCH (v:Variable {name: $target_name})
MERGE (f)-[r:RETURNS {line: $line, seq: $seq}]->(v)
SET r.control_context = $control_context,
    r.branch = $branch
RETURN r
"""

# Data flow edge MERGE queries (TICKET-203/205)
MERGE_PASSES_TO = """
MATCH (src:Variable {name: $source_name})
MATCH (tgt:Variable {name: $target_name})
MERGE (src)-[r:PASSES_TO {call_line: $call_line}]->(tgt)
SET r.seq = $seq,
    r.arg_position = $arg_position,
    r.arg_keyword = $arg_keyword
RETURN r
"""

MERGE_FEEDS = """
MATCH (src:Variable {name: $source_name})
MATCH (tgt:Variable {name: $target_name})
MERGE (src)-[r:FEEDS {line: $line, seq: $seq}]->(tgt)
SET r.expression_text = $expression_text,
    r.via = $via
RETURN r
"""

# --- Query templates (Sprint 0 + TICKET-501) ---

GET_NODES_PAGINATED = """
MATCH (n)
WHERE ($label = '' OR labels(n)[0] = $label)
RETURN n
SKIP $offset
LIMIT $limit
"""

GET_NODE_WITH_EDGES = """
MATCH (n)
WHERE ID(n) = $node_id
OPTIONAL MATCH (n)-[r]-(m)
RETURN n, collect(DISTINCT r) AS rels, collect(DISTINCT m) AS neighbors
"""

GET_VARIABLE_BY_NAME = """
MATCH (v:Variable)
WHERE v.name = $name
RETURN v
"""

GET_VARIABLE_TIMELINE = """
MATCH (v:Variable {name: $variable_name})
OPTIONAL MATCH (f:Function)-[a:ASSIGNS]->(v) RETURN 'ASSIGNS' AS edge_type, f.name AS func_name, v.name AS var_name, a.line AS line, a.seq AS seq, properties(a) AS props
UNION ALL
MATCH (v:Variable {name: $variable_name})
OPTIONAL MATCH (f:Function)-[m:MUTATES]->(v) RETURN 'MUTATES' AS edge_type, f.name AS func_name, v.name AS var_name, m.line AS line, m.seq AS seq, properties(m) AS props
UNION ALL
MATCH (v:Variable {name: $variable_name})
OPTIONAL MATCH (f:Function)-[r:READS]->(v) RETURN 'READS' AS edge_type, f.name AS func_name, v.name AS var_name, r.line AS line, r.seq AS seq, properties(r) AS props
UNION ALL
MATCH (v:Variable {name: $variable_name})
OPTIONAL MATCH (f:Function)-[ret:RETURNS]->(v) RETURN 'RETURNS' AS edge_type, f.name AS func_name, v.name AS var_name, ret.line AS line, ret.seq AS seq, properties(ret) AS props
UNION ALL
MATCH (v:Variable {name: $variable_name})
OPTIONAL MATCH (v)-[p:PASSES_TO]->(t:Variable) RETURN 'PASSES_TO' AS edge_type, '' AS func_name, t.name AS var_name, p.call_line AS line, p.seq AS seq, properties(p) AS props
UNION ALL
MATCH (v:Variable {name: $variable_name})
OPTIONAL MATCH (src:Variable)-[fd:FEEDS]->(v) RETURN 'FEEDS' AS edge_type, '' AS func_name, src.name AS var_name, fd.line AS line, fd.seq AS seq, properties(fd) AS props
"""

SEARCH_VARIABLES = """
MATCH (v:Variable)
WHERE v.name CONTAINS $name
RETURN v
LIMIT 50
"""

SEARCH_VARIABLES_WITH_SCOPE = """
MATCH (v:Variable)
WHERE v.name CONTAINS $name AND v.scope CONTAINS $scope
RETURN v
LIMIT 50
"""

# --- Batch UNWIND templates (for BatchUpserter) ---

BATCH_MERGE_MODULES = """
UNWIND $items AS item
MERGE (m:Module {name: item.name})
SET m.start_line = item.start_line,
    m.end_line = item.end_line,
    m.module_path = item.module_path,
    m.checksum = item.checksum
"""

BATCH_MERGE_CLASSES = """
UNWIND $items AS item
MERGE (c:Class {name: item.name})
SET c.start_line = item.start_line,
    c.end_line = item.end_line,
    c.start_col = item.start_col,
    c.end_col = item.end_col,
    c.source_text = item.source_text,
    c.module_path = item.module_path,
    c.decorators = item.decorators,
    c.docstring = item.docstring
"""

BATCH_MERGE_FUNCTIONS = """
UNWIND $items AS item
MERGE (f:Function {name: item.name})
SET f.start_line = item.start_line,
    f.end_line = item.end_line,
    f.start_col = item.start_col,
    f.end_col = item.end_col,
    f.source_text = item.source_text,
    f.module_path = item.module_path,
    f.params = item.params,
    f.decorators = item.decorators,
    f.docstring = item.docstring,
    f.is_async = item.is_async
"""

BATCH_MERGE_DEFINES = """
UNWIND $items AS item
MATCH (parent {name: item.source_name})
MATCH (child {name: item.target_name})
MERGE (parent)-[:DEFINES]->(child)
"""

BATCH_MERGE_CALLS = """
UNWIND $items AS item
MATCH (caller:Function {name: item.source_name})
MATCH (callee {name: item.target_name})
MERGE (caller)-[r:CALLS {call_line: item.call_line}]->(callee)
SET r.seq = item.seq,
    r.call_order = item.call_order
"""

BATCH_MERGE_INHERITS = """
UNWIND $items AS item
MATCH (child:Class {name: item.source_name})
MATCH (parent:Class {name: item.target_name})
MERGE (child)-[:INHERITS]->(parent)
"""

BATCH_MERGE_IMPORTS = """
UNWIND $items AS item
MATCH (importer:Module {name: item.source_name})
MATCH (imported:Module {name: item.target_name})
MERGE (importer)-[r:IMPORTS]->(imported)
SET r.alias = item.alias
"""

BATCH_MERGE_STATEMENTS = """
UNWIND $items AS item
MERGE (s:Statement {name: item.name})
SET s.kind = item.kind,
    s.source_text = item.source_text,
    s.start_line = item.start_line,
    s.end_line = item.end_line,
    s.start_col = item.start_col,
    s.end_col = item.end_col,
    s.seq = item.seq,
    s.module_path = item.module_path
"""

BATCH_MERGE_CONTROL_FLOWS = """
UNWIND $items AS item
MERGE (cf:ControlFlow {name: item.name})
SET cf.kind = item.kind,
    cf.condition_text = item.condition_text,
    cf.source_text = item.source_text,
    cf.start_line = item.start_line,
    cf.end_line = item.end_line,
    cf.start_col = item.start_col,
    cf.end_col = item.end_col,
    cf.seq = item.seq,
    cf.module_path = item.module_path
"""

BATCH_MERGE_BRANCHES = """
UNWIND $items AS item
MERGE (b:Branch {name: item.name})
SET b.kind = item.kind,
    b.condition_text = item.condition_text,
    b.source_text = item.source_text,
    b.start_line = item.start_line,
    b.end_line = item.end_line,
    b.start_col = item.start_col,
    b.end_col = item.end_col,
    b.seq = item.seq,
    b.module_path = item.module_path
"""

BATCH_MERGE_CONTAINS = """
UNWIND $items AS item
MATCH (parent {name: item.source_name})
MATCH (child {name: item.target_name})
MERGE (parent)-[:CONTAINS]->(child)
"""

BATCH_MERGE_NEXT = """
UNWIND $items AS item
MATCH (prev {name: item.source_name})
MATCH (next {name: item.target_name})
MERGE (prev)-[:NEXT]->(next)
"""

BATCH_MERGE_VARIABLES = """
UNWIND $items AS item
MERGE (v:Variable {name: item.name})
SET v.scope = item.scope,
    v.origin_line = item.origin_line,
    v.origin_func = item.origin_func,
    v.type_hint = item.type_hint,
    v.module_path = item.module_path
"""

BATCH_MERGE_ASSIGNS = """
UNWIND $items AS item
MATCH (f:Function {name: item.source_name})
MATCH (v:Variable {name: item.target_name})
MERGE (f)-[r:ASSIGNS {line: item.line, seq: item.seq}]->(v)
SET r.col = item.col,
    r.is_rebind = item.is_rebind,
    r.control_context = item.control_context,
    r.branch = item.branch
"""

BATCH_MERGE_MUTATES = """
UNWIND $items AS item
MATCH (f:Function {name: item.source_name})
MATCH (v:Variable {name: item.target_name})
MERGE (f)-[r:MUTATES {line: item.line, seq: item.seq}]->(v)
SET r.mutation_kind = item.mutation_kind,
    r.control_context = item.control_context,
    r.branch = item.branch
"""

BATCH_MERGE_READS = """
UNWIND $items AS item
MATCH (f:Function {name: item.source_name})
MATCH (v:Variable {name: item.target_name})
MERGE (f)-[r:READS {line: item.line, seq: item.seq}]->(v)
SET r.control_context = item.control_context,
    r.branch = item.branch
"""

BATCH_MERGE_RETURNS = """
UNWIND $items AS item
MATCH (f:Function {name: item.source_name})
MATCH (v:Variable {name: item.target_name})
MERGE (f)-[r:RETURNS {line: item.line, seq: item.seq}]->(v)
SET r.control_context = item.control_context,
    r.branch = item.branch
"""

BATCH_MERGE_PASSES_TO = """
UNWIND $items AS item
MATCH (src:Variable {name: item.source_name})
MATCH (tgt:Variable {name: item.target_name})
MERGE (src)-[r:PASSES_TO {call_line: item.call_line}]->(tgt)
SET r.seq = item.seq,
    r.arg_position = item.arg_position,
    r.arg_keyword = item.arg_keyword
"""

BATCH_MERGE_FEEDS = """
UNWIND $items AS item
MATCH (src:Variable {name: item.source_name})
MATCH (tgt:Variable {name: item.target_name})
MERGE (src)-[r:FEEDS {line: item.line, seq: item.seq}]->(tgt)
SET r.expression_text = item.expression_text,
    r.via = item.via
"""

# TICKET-501: Logic Pack query templates

GET_CALL_CHAIN = """
MATCH path = (f:Function {name: $function_name})-[:CALLS*1..$hops]->(g:Function)
UNWIND nodes(path) AS n
WITH collect(DISTINCT n) AS funcs, path
UNWIND relationships(path) AS r
RETURN collect(DISTINCT {source: startNode(r).name, target: endNode(r).name, type: type(r), props: properties(r)}) AS edges,
       [f IN collect(DISTINCT nodes(path)) | head(f)] AS raw_nodes
"""

GET_IMPACT = """
MATCH (f:Function {name: $function_name})-[:MUTATES]->(v:Variable)
OPTIONAL MATCH (consumer:Function)-[:READS]->(v)
RETURN f, v, collect(DISTINCT consumer) AS consumers
"""

GET_CLASS_HIERARCHY = """
MATCH path = (c:Class {name: $class_name})-[:INHERITS*0..5]->(parent:Class)
OPTIONAL MATCH (cls)-[:DEFINES]->(method:Function)
WHERE cls IN nodes(path)
RETURN nodes(path) AS classes, collect(DISTINCT method) AS methods
"""

GET_FUNCTION_FLOW = """
MATCH (f:Function {name: $function_name})-[:CONTAINS*1..8]->(child)
OPTIONAL MATCH (child)-[next:NEXT]->(sibling)
RETURN f, collect(DISTINCT child) AS children, collect(DISTINCT {source: child.name, target: sibling.name, type: 'NEXT'}) AS next_edges
"""

GET_LOGIC_PACK_SUBGRAPH = """
MATCH (center {name: $node_name})
CALL {
    WITH center
    MATCH (center)-[r*1..$hops]-(neighbor)
    RETURN collect(DISTINCT neighbor) AS neighbors, [rel IN collect(DISTINCT last(r)) | rel] AS rels
}
RETURN center, neighbors, rels
"""
