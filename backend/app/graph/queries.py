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
