"""Cypher query templates for the Code-as-Data graph schema (TICKET-801).

All queries use UUID-based identity. The original queries.py is preserved for
backward compatibility with the existing indexer; these new queries power the
800-series LogicNode/Variable/Flow operations.
"""

from __future__ import annotations


# --- Schema initialization ---

CREATE_INDEXES = """
CREATE INDEX FOR (n:LogicNode) ON (n.id);
CREATE INDEX FOR (n:LogicNode) ON (n.ast_hash);
CREATE INDEX FOR (n:LogicNode) ON (n.structural_hash);
CREATE INDEX FOR (n:LogicNode) ON (n.name);
CREATE INDEX FOR (n:LogicNode) ON (n.kind);
CREATE INDEX FOR (n:LogicNode) ON (n.module_path);
CREATE INDEX FOR (n:LogicNode) ON (n.status);
CREATE INDEX FOR (v:Variable) ON (v.id);
CREATE INDEX FOR (v:Variable) ON (v.name);
CREATE INDEX FOR (v:Variable) ON (v.scope);
CREATE INDEX FOR (v:Variable) ON (v.origin_node_id);
CREATE INDEX FOR (f:Flow) ON (f.id);
CREATE INDEX FOR (f:Flow) ON (f.name);
CREATE INDEX FOR (f:Flow) ON (f.parent_flow_id);
CREATE INDEX FOR (n:LogicNode) ON (n.module_path, n.name)
"""

# Split into individual statements for execution
INDEX_STATEMENTS: list[str] = [stmt.strip().rstrip(";") for stmt in CREATE_INDEXES.strip().split(";") if stmt.strip()]


# --- LogicNode CRUD ---

MERGE_LOGIC_NODE = """
MERGE (n:LogicNode {id: $id})
SET n.ast_hash = $ast_hash,
    n.structural_hash = $structural_hash,
    n.kind = $kind,
    n.name = $name,
    n.module_path = $module_path,
    n.signature = $signature,
    n.source_text = $source_text,
    n.semantic_intent = $semantic_intent,
    n.docstring = $docstring,
    n.decorators = $decorators,
    n.params = $params,
    n.return_type = $return_type,
    n.tags = $tags,
    n.class_id = $class_id,
    n.derived_from = $derived_from,
    n.start_line = $start_line,
    n.end_line = $end_line,
    n.status = $status,
    n.created_at = $created_at,
    n.updated_at = $updated_at
RETURN n
"""

GET_LOGIC_NODE_BY_ID = """
MATCH (n:LogicNode {id: $id})
RETURN n
"""

FIND_LOGIC_NODES = """
MATCH (n:LogicNode)
WHERE n.status = 'active'
  AND ($query = '' OR n.name CONTAINS $query OR n.semantic_intent CONTAINS $query)
  AND ($kind = '' OR n.kind = $kind)
RETURN n
ORDER BY n.name
SKIP $offset
LIMIT $limit
"""

FIND_LOGIC_NODES_BY_TAG = """
MATCH (n:LogicNode)
WHERE n.status = 'active'
  AND $tag IN n.tags
RETURN n
ORDER BY n.name
SKIP $offset
LIMIT $limit
"""

DEPRECATE_LOGIC_NODE = """
MATCH (n:LogicNode {id: $id})
SET n.status = 'deprecated',
    n.updated_at = $updated_at
RETURN n
"""

DELETE_LOGIC_NODE_VARIABLES = """
MATCH (n:LogicNode {id: $node_id})-[:ASSIGNS|MUTATES|READS|RETURNS]->(v:Variable)
WHERE v.origin_node_id = $node_id
DETACH DELETE v
"""

GET_ALL_LOGIC_NODES = """
MATCH (n:LogicNode)
WHERE n.status = 'active'
RETURN n
ORDER BY n.name
"""

# Lightweight overview queries — return only the fields needed for the
# knowledge-graph canvas (no source_text, no params, etc.)
GRAPH_OVERVIEW_NODES = """
MATCH (n:LogicNode)
WHERE n.status = 'active' AND n.kind IN $kinds
RETURN n.id AS id, n.kind AS kind, n.name AS name, n.module_path AS module_path
ORDER BY n.name
"""

GRAPH_OVERVIEW_EDGES = """
MATCH (s:LogicNode)-[r]->(t:LogicNode)
WHERE s.status = 'active' AND t.status = 'active'
  AND s.kind IN $kinds AND t.kind IN $kinds
RETURN type(r) AS type, s.id AS source, t.id AS target
"""


# --- Variable CRUD ---

MERGE_VARIABLE = """
MERGE (v:Variable {id: $id})
SET v.name = $name,
    v.scope = $scope,
    v.origin_node_id = $origin_node_id,
    v.origin_line = $origin_line,
    v.type_hint = $type_hint,
    v.is_parameter = $is_parameter,
    v.is_attribute = $is_attribute,
    v.created_at = $created_at
RETURN v
"""

GET_VARIABLE_BY_ID = """
MATCH (v:Variable {id: $id})
RETURN v
"""

SEARCH_VARIABLES_BY_NAME = """
MATCH (v:Variable)
WHERE v.name CONTAINS $name
  AND ($scope = '' OR v.scope CONTAINS $scope)
RETURN v
LIMIT $limit
"""

DELETE_VARIABLES_FOR_NODE = """
MATCH (v:Variable {origin_node_id: $node_id})
DETACH DELETE v
"""

GET_ALL_VARIABLES = """
MATCH (v:Variable)
RETURN v
"""

GET_VARIABLES_FOR_NODE = """
MATCH (n:LogicNode {id: $node_id})-[r:ASSIGNS|MUTATES|READS|RETURNS]->(v:Variable)
RETURN v.id AS id, v.name AS name, v.type_hint AS type_hint,
       v.is_parameter AS is_parameter, v.is_attribute AS is_attribute,
       type(r) AS edge_type
"""


# --- Edge operations ---

# Generic edge creation by type - each edge type has its own template
# because FalkorDB Cypher requires literal relationship types

MERGE_EDGE_CALLS = """
MATCH (s:LogicNode {id: $source_id})
MATCH (t:LogicNode {id: $target_id})
MERGE (s)-[r:CALLS]->(t)
SET r += $properties
RETURN s, r, t
"""

MERGE_EDGE_DEPENDS_ON = """
MATCH (s:LogicNode {id: $source_id})
MATCH (t:LogicNode {id: $target_id})
MERGE (s)-[r:DEPENDS_ON]->(t)
SET r += $properties
RETURN s, r, t
"""

MERGE_EDGE_IMPLEMENTS = """
MATCH (s:LogicNode {id: $source_id})
MATCH (t:LogicNode {id: $target_id})
MERGE (s)-[r:IMPLEMENTS]->(t)
SET r += $properties
RETURN s, r, t
"""

MERGE_EDGE_VALIDATES = """
MATCH (s:LogicNode {id: $source_id})
MATCH (t:LogicNode {id: $target_id})
MERGE (s)-[r:VALIDATES]->(t)
SET r += $properties
RETURN s, r, t
"""

MERGE_EDGE_TRANSFORMS = """
MATCH (s:LogicNode {id: $source_id})
MATCH (t:LogicNode {id: $target_id})
MERGE (s)-[r:TRANSFORMS]->(t)
SET r += $properties
RETURN s, r, t
"""

MERGE_EDGE_INHERITS = """
MATCH (s:LogicNode {id: $source_id})
MATCH (t:LogicNode {id: $target_id})
MERGE (s)-[r:INHERITS]->(t)
SET r += $properties
RETURN s, r, t
"""

MERGE_EDGE_MEMBER_OF = """
MATCH (s:LogicNode {id: $source_id})
MATCH (t:LogicNode {id: $target_id})
MERGE (s)-[r:MEMBER_OF]->(t)
SET r += $properties
RETURN s, r, t
"""

# LogicNode -> Variable edges

MERGE_EDGE_ASSIGNS = """
MATCH (s:LogicNode {id: $source_id})
MATCH (t:Variable {id: $target_id})
MERGE (s)-[r:ASSIGNS]->(t)
SET r += $properties
RETURN s, r, t
"""

MERGE_EDGE_MUTATES = """
MATCH (s:LogicNode {id: $source_id})
MATCH (t:Variable {id: $target_id})
MERGE (s)-[r:MUTATES]->(t)
SET r += $properties
RETURN s, r, t
"""

MERGE_EDGE_READS = """
MATCH (s:LogicNode {id: $source_id})
MATCH (t:Variable {id: $target_id})
MERGE (s)-[r:READS]->(t)
SET r += $properties
RETURN s, r, t
"""

MERGE_EDGE_RETURNS = """
MATCH (s:LogicNode {id: $source_id})
MATCH (t:Variable {id: $target_id})
MERGE (s)-[r:RETURNS]->(t)
SET r += $properties
RETURN s, r, t
"""

# Variable -> Variable edges

MERGE_EDGE_PASSES_TO = """
MATCH (s:Variable {id: $source_id})
MATCH (t:Variable {id: $target_id})
MERGE (s)-[r:PASSES_TO]->(t)
SET r += $properties
RETURN s, r, t
"""

MERGE_EDGE_FEEDS = """
MATCH (s:Variable {id: $source_id})
MATCH (t:Variable {id: $target_id})
MERGE (s)-[r:FEEDS]->(t)
SET r += $properties
RETURN s, r, t
"""

# Flow edges

MERGE_EDGE_STEP_OF = """
MATCH (s:LogicNode {id: $source_id})
MATCH (t:Flow {id: $target_id})
MERGE (s)-[r:STEP_OF]->(t)
SET r += $properties
RETURN s, r, t
"""

MERGE_EDGE_CONTAINS_FLOW = """
MATCH (s:Flow {id: $source_id})
MATCH (t:Flow {id: $target_id})
MERGE (s)-[r:CONTAINS_FLOW]->(t)
SET r += $properties
RETURN s, r, t
"""

MERGE_EDGE_PROMOTED_TO = """
MATCH (s:Flow {id: $source_id})
MATCH (t:LogicNode {id: $target_id})
MERGE (s)-[r:PROMOTED_TO]->(t)
RETURN s, r, t
"""

# Mapping from edge type string to its query template
EDGE_MERGE_QUERIES: dict[str, str] = {
    "CALLS": MERGE_EDGE_CALLS,
    "DEPENDS_ON": MERGE_EDGE_DEPENDS_ON,
    "IMPLEMENTS": MERGE_EDGE_IMPLEMENTS,
    "VALIDATES": MERGE_EDGE_VALIDATES,
    "TRANSFORMS": MERGE_EDGE_TRANSFORMS,
    "INHERITS": MERGE_EDGE_INHERITS,
    "MEMBER_OF": MERGE_EDGE_MEMBER_OF,
    "ASSIGNS": MERGE_EDGE_ASSIGNS,
    "MUTATES": MERGE_EDGE_MUTATES,
    "READS": MERGE_EDGE_READS,
    "RETURNS": MERGE_EDGE_RETURNS,
    "PASSES_TO": MERGE_EDGE_PASSES_TO,
    "FEEDS": MERGE_EDGE_FEEDS,
    "STEP_OF": MERGE_EDGE_STEP_OF,
    "CONTAINS_FLOW": MERGE_EDGE_CONTAINS_FLOW,
    "PROMOTED_TO": MERGE_EDGE_PROMOTED_TO,
}


# Delete edge by type

DELETE_EDGE_TEMPLATE = """
MATCH (s {{id: $source_id}})-[r:{edge_type}]->(t {{id: $target_id}})
DELETE r
"""

# Get edges for a node (outgoing)
GET_OUTGOING_EDGES = """
MATCH (n {id: $node_id})-[r]->(m)
WHERE $edge_types = [] OR type(r) IN $edge_types
RETURN type(r) AS edge_type, n.id AS source, m.id AS target, properties(r) AS props
"""

# Get edges for a node (incoming)
GET_INCOMING_EDGES = """
MATCH (m)-[r]->(n {id: $node_id})
WHERE $edge_types = [] OR type(r) IN $edge_types
RETURN type(r) AS edge_type, m.id AS source, n.id AS target, properties(r) AS props
"""

# Multi-hop dependency traversal (outgoing)
GET_DEPENDENCIES = """
MATCH (root:LogicNode {id: $node_id})
CALL {
    WITH root
    MATCH path = (root)-[:CALLS|DEPENDS_ON|IMPLEMENTS|VALIDATES|TRANSFORMS*1..$depth]->(dep:LogicNode)
    WHERE dep.status = 'active'
    RETURN dep, relationships(path) AS rels
}
RETURN root, collect(DISTINCT dep) AS dependencies,
       [r IN collect(rels) | head(r)] AS edges
"""

# Multi-hop dependent traversal (incoming)
GET_DEPENDENTS = """
MATCH (root:LogicNode {id: $node_id})
CALL {
    WITH root
    MATCH path = (root)<-[:CALLS|DEPENDS_ON|IMPLEMENTS|VALIDATES|TRANSFORMS*1..$depth]-(dep:LogicNode)
    WHERE dep.status = 'active'
    RETURN dep, relationships(path) AS rels
}
RETURN root, collect(DISTINCT dep) AS dependents,
       [r IN collect(rels) | head(r)] AS edges
"""

GET_ALL_EDGES = """
MATCH (s)-[r]->(t)
WHERE (s:LogicNode OR s:Variable OR s:Flow)
  AND (t:LogicNode OR t:Variable OR t:Flow)
  AND s.id IS NOT NULL
  AND t.id IS NOT NULL
RETURN type(r) AS edge_type, s.id AS source, t.id AS target, properties(r) AS props
"""


# --- Mutation Timeline Query (schema.md Section 6.1) ---

MUTATION_TIMELINE = """
MATCH (v:Variable {id: $variable_id})
OPTIONAL MATCH (origin:LogicNode)-[a:ASSIGNS]->(v) WHERE a.is_rebind = false
OPTIONAL MATCH (mutator:LogicNode)-[m:MUTATES]->(v)
OPTIONAL MATCH (reader:LogicNode)-[r:READS]->(v)
OPTIONAL MATCH (returner:LogicNode)-[ret:RETURNS]->(v)
OPTIONAL MATCH (v)-[p:PASSES_TO]->(downstream:Variable)
OPTIONAL MATCH (upstream:Variable)-[p2:PASSES_TO]->(v)
OPTIONAL MATCH (feeder:Variable)-[f:FEEDS]->(v)
OPTIONAL MATCH (v)-[f2:FEEDS]->(fed:Variable)
RETURN v, origin, a, mutator, m, reader, r, returner, ret,
       downstream, p, upstream, p2, feeder, f, fed, f2
"""


# --- Deduplication Check (schema.md Section 6.3) ---

CHECK_DUPLICATE = """
MATCH (existing:LogicNode {ast_hash: $ast_hash, status: 'active'})
WHERE existing.id <> $current_id
RETURN existing.id AS id, existing.name AS name, existing.module_path AS module_path
"""


# --- Impact Analysis (schema.md Section 6.4) ---

IMPACT_ANALYSIS = """
MATCH (changed:LogicNode {id: $node_id})-[:MUTATES]->(v:Variable)
MATCH (consumer:LogicNode)-[:READS]->(v)
WHERE consumer.id <> changed.id AND consumer.status = 'active'
RETURN v.name AS variable, v.id AS variable_id,
       collect(DISTINCT {id: consumer.id, name: consumer.name}) AS affected_consumers
"""


# --- Logic Pack / Dependency Subgraph (schema.md Section 6.2) ---

LOGIC_PACK_SUBGRAPH = """
MATCH (root:LogicNode {id: $node_id})
CALL {
    WITH root
    MATCH path = (root)-[:CALLS|DEPENDS_ON*1..$depth]->(dep:LogicNode)
    WHERE dep.status = 'active'
    RETURN dep, relationships(path) AS rels
}
RETURN root, collect(DISTINCT dep) AS dependencies, collect(rels) AS edges
"""


# --- Flow operations ---

MERGE_FLOW = """
MERGE (f:Flow {id: $id})
SET f.name = $name,
    f.description = $description,
    f.entry_point = $entry_point,
    f.exit_points = $exit_points,
    f.node_ids = $node_ids,
    f.sub_flow_ids = $sub_flow_ids,
    f.parent_flow_id = $parent_flow_id,
    f.promoted_node_id = $promoted_node_id,
    f.created_at = $created_at,
    f.updated_at = $updated_at
RETURN f
"""

GET_FLOW_BY_ID = """
MATCH (f:Flow {id: $id})
RETURN f
"""

GET_ALL_FLOWS = """
MATCH (f:Flow)
RETURN f
ORDER BY f.name
"""

DELETE_FLOW = """
MATCH (f:Flow {id: $id})
DETACH DELETE f
"""

# Flow traversal (schema.md Section 6.5)
FLOW_TRAVERSAL = """
MATCH (f:Flow {id: $flow_id})
MATCH (n:LogicNode)-[s:STEP_OF]->(f)
WITH f, n, s ORDER BY s.step_order
OPTIONAL MATCH (n)-[e:CALLS|DEPENDS_ON|TRANSFORMS]->(next:LogicNode)
WHERE next.id IN f.node_ids
OPTIONAL MATCH (f)-[cf:CONTAINS_FLOW]->(sub:Flow)
RETURN collect(DISTINCT {node: n, step: s.step_order}) AS steps,
       collect(DISTINCT {edge: e, from_id: n.id, to_id: next.id}) AS connections,
       collect(DISTINCT {sub_flow: sub, order: cf.step_order}) AS sub_flows
"""

# Flow hierarchy (schema.md Section 6.6)
FLOW_HIERARCHY = """
MATCH (root:Flow {id: $flow_id})
CALL {
    WITH root
    MATCH path = (root)-[:CONTAINS_FLOW*1..5]->(descendant:Flow)
    RETURN descendant, length(path) AS depth, relationships(path) AS rels
}
RETURN root, collect({flow: descendant, depth: depth}) AS hierarchy
"""


# --- Batch operations ---

BATCH_MERGE_LOGIC_NODES = """
UNWIND $items AS item
MERGE (n:LogicNode {id: item.id})
SET n.ast_hash = item.ast_hash,
    n.structural_hash = item.structural_hash,
    n.kind = item.kind,
    n.name = item.name,
    n.module_path = item.module_path,
    n.signature = item.signature,
    n.source_text = item.source_text,
    n.semantic_intent = item.semantic_intent,
    n.docstring = item.docstring,
    n.decorators = item.decorators,
    n.params = item.params,
    n.return_type = item.return_type,
    n.tags = item.tags,
    n.class_id = item.class_id,
    n.derived_from = item.derived_from,
    n.start_line = item.start_line,
    n.end_line = item.end_line,
    n.status = item.status,
    n.created_at = item.created_at,
    n.updated_at = item.updated_at
"""

BATCH_MERGE_VARIABLES = """
UNWIND $items AS item
MERGE (v:Variable {id: item.id})
SET v.name = item.name,
    v.scope = item.scope,
    v.origin_node_id = item.origin_node_id,
    v.origin_line = item.origin_line,
    v.type_hint = item.type_hint,
    v.is_parameter = item.is_parameter,
    v.is_attribute = item.is_attribute,
    v.created_at = item.created_at
"""

BATCH_MERGE_FLOWS = """
UNWIND $items AS item
MERGE (f:Flow {id: item.id})
SET f.name = item.name,
    f.description = item.description,
    f.entry_point = item.entry_point,
    f.exit_points = item.exit_points,
    f.node_ids = item.node_ids,
    f.sub_flow_ids = item.sub_flow_ids,
    f.parent_flow_id = item.parent_flow_id,
    f.promoted_node_id = item.promoted_node_id,
    f.created_at = item.created_at,
    f.updated_at = item.updated_at
"""

# --- Batch edge operations (UNWIND) ---
# FalkorDB requires literal relationship types, so each edge type needs its own template.

BATCH_MERGE_EDGES_CALLS = """
UNWIND $items AS item
MATCH (s:LogicNode {id: item.source_id})
MATCH (t:LogicNode {id: item.target_id})
MERGE (s)-[r:CALLS]->(t)
SET r.weight = coalesce(item.weight, 1)
"""

BATCH_MERGE_EDGES_DEPENDS_ON = """
UNWIND $items AS item
MATCH (s:LogicNode {id: item.source_id})
MATCH (t:LogicNode {id: item.target_id})
MERGE (s)-[r:DEPENDS_ON]->(t)
SET r.weight = coalesce(item.weight, 1)
"""

BATCH_MERGE_EDGES_IMPLEMENTS = """
UNWIND $items AS item
MATCH (s:LogicNode {id: item.source_id})
MATCH (t:LogicNode {id: item.target_id})
MERGE (s)-[r:IMPLEMENTS]->(t)
SET r.weight = coalesce(item.weight, 1)
"""

BATCH_MERGE_EDGES_VALIDATES = """
UNWIND $items AS item
MATCH (s:LogicNode {id: item.source_id})
MATCH (t:LogicNode {id: item.target_id})
MERGE (s)-[r:VALIDATES]->(t)
SET r.weight = coalesce(item.weight, 1)
"""

BATCH_MERGE_EDGES_TRANSFORMS = """
UNWIND $items AS item
MATCH (s:LogicNode {id: item.source_id})
MATCH (t:LogicNode {id: item.target_id})
MERGE (s)-[r:TRANSFORMS]->(t)
SET r.weight = coalesce(item.weight, 1)
"""

BATCH_MERGE_EDGES_INHERITS = """
UNWIND $items AS item
MATCH (s:LogicNode {id: item.source_id})
MATCH (t:LogicNode {id: item.target_id})
MERGE (s)-[r:INHERITS]->(t)
SET r.weight = coalesce(item.weight, 1)
"""

BATCH_MERGE_EDGES_MEMBER_OF = """
UNWIND $items AS item
MATCH (s:LogicNode {id: item.source_id})
MATCH (t:LogicNode {id: item.target_id})
MERGE (s)-[r:MEMBER_OF]->(t)
SET r.access = coalesce(item.access, 'public')
"""

BATCH_MERGE_EDGES_ASSIGNS = """
UNWIND $items AS item
MATCH (s:LogicNode {id: item.source_id})
MATCH (t:Variable {id: item.target_id})
MERGE (s)-[r:ASSIGNS]->(t)
SET r.is_rebind = coalesce(item.is_rebind, false)
"""

BATCH_MERGE_EDGES_MUTATES = """
UNWIND $items AS item
MATCH (s:LogicNode {id: item.source_id})
MATCH (t:Variable {id: item.target_id})
MERGE (s)-[r:MUTATES]->(t)
SET r.weight = coalesce(item.weight, 1)
"""

BATCH_MERGE_EDGES_READS = """
UNWIND $items AS item
MATCH (s:LogicNode {id: item.source_id})
MATCH (t:Variable {id: item.target_id})
MERGE (s)-[r:READS]->(t)
SET r.weight = coalesce(item.weight, 1)
"""

BATCH_MERGE_EDGES_RETURNS = """
UNWIND $items AS item
MATCH (s:LogicNode {id: item.source_id})
MATCH (t:Variable {id: item.target_id})
MERGE (s)-[r:RETURNS]->(t)
SET r.weight = coalesce(item.weight, 1)
"""

BATCH_MERGE_EDGES_PASSES_TO = """
UNWIND $items AS item
MATCH (s:Variable {id: item.source_id})
MATCH (t:Variable {id: item.target_id})
MERGE (s)-[r:PASSES_TO]->(t)
SET r.weight = coalesce(item.weight, 1)
"""

BATCH_MERGE_EDGES_FEEDS = """
UNWIND $items AS item
MATCH (s:Variable {id: item.source_id})
MATCH (t:Variable {id: item.target_id})
MERGE (s)-[r:FEEDS]->(t)
SET r.weight = coalesce(item.weight, 1)
"""

BATCH_MERGE_EDGES_STEP_OF = """
UNWIND $items AS item
MATCH (s:LogicNode {id: item.source_id})
MATCH (t:Flow {id: item.target_id})
MERGE (s)-[r:STEP_OF]->(t)
SET r.step_order = item.step_order
"""

BATCH_MERGE_EDGES_CONTAINS_FLOW = """
UNWIND $items AS item
MATCH (s:Flow {id: item.source_id})
MATCH (t:Flow {id: item.target_id})
MERGE (s)-[r:CONTAINS_FLOW]->(t)
SET r.step_order = item.step_order
"""

BATCH_MERGE_EDGES_PROMOTED_TO = """
UNWIND $items AS item
MATCH (s:Flow {id: item.source_id})
MATCH (t:LogicNode {id: item.target_id})
MERGE (s)-[r:PROMOTED_TO]->(t)
"""

# Mapping from edge type string to batch UNWIND query template
BATCH_EDGE_MERGE_QUERIES: dict[str, str] = {
    "CALLS": BATCH_MERGE_EDGES_CALLS,
    "DEPENDS_ON": BATCH_MERGE_EDGES_DEPENDS_ON,
    "IMPLEMENTS": BATCH_MERGE_EDGES_IMPLEMENTS,
    "VALIDATES": BATCH_MERGE_EDGES_VALIDATES,
    "TRANSFORMS": BATCH_MERGE_EDGES_TRANSFORMS,
    "INHERITS": BATCH_MERGE_EDGES_INHERITS,
    "MEMBER_OF": BATCH_MERGE_EDGES_MEMBER_OF,
    "ASSIGNS": BATCH_MERGE_EDGES_ASSIGNS,
    "MUTATES": BATCH_MERGE_EDGES_MUTATES,
    "READS": BATCH_MERGE_EDGES_READS,
    "RETURNS": BATCH_MERGE_EDGES_RETURNS,
    "PASSES_TO": BATCH_MERGE_EDGES_PASSES_TO,
    "FEEDS": BATCH_MERGE_EDGES_FEEDS,
    "STEP_OF": BATCH_MERGE_EDGES_STEP_OF,
    "CONTAINS_FLOW": BATCH_MERGE_EDGES_CONTAINS_FLOW,
    "PROMOTED_TO": BATCH_MERGE_EDGES_PROMOTED_TO,
}

# Batch lookup for incremental imports — eliminates N+1 _find_existing_node calls
BATCH_FIND_EXISTING_NODES = """
UNWIND $lookups AS lk
OPTIONAL MATCH (n:LogicNode {name: lk.name, module_path: lk.module_path, status: 'active'})
RETURN lk.name AS name, lk.module_path AS module_path, n.id AS id, n.ast_hash AS ast_hash
"""

# --- Compose: suggestion queries (TICKET-910) ---

FIND_NODES_BY_PARAM_TYPE = """
MATCH (n:LogicNode)
WHERE n.status = 'active' AND n.params CONTAINS $type_hint
RETURN n.id AS id, n.name AS name, n.params AS params,
       n.signature AS signature, n.return_type AS return_type
LIMIT $limit
"""

FIND_NODES_BY_RETURN_TYPE = """
MATCH (n:LogicNode)
WHERE n.status = 'active' AND n.return_type = $type_hint
RETURN n.id AS id, n.name AS name, n.params AS params,
       n.signature AS signature, n.return_type AS return_type
LIMIT $limit
"""

FIND_NODES_BY_PARAM_NAME = """
MATCH (n:LogicNode)
WHERE n.status = 'active' AND n.params CONTAINS $param_name
RETURN n.id AS id, n.name AS name, n.params AS params,
       n.signature AS signature, n.return_type AS return_type
LIMIT $limit
"""

# --- Compose: assembly queries ---

GET_CLASS_FOR_METHOD = """
MATCH (m:LogicNode {id: $method_id})-[:MEMBER_OF]->(c:LogicNode {kind: 'class'})
OPTIONAL MATCH (init:LogicNode)-[:MEMBER_OF]->(c)
WHERE init.name ENDS WITH '.__init__'
RETURN c.id AS class_id, c.name AS class_name, c.source_text AS class_source,
       init.id AS init_id, init.params AS init_params
"""

GET_NODE_DATA_FLOW = """
MATCH (n:LogicNode {id: $node_id})
OPTIONAL MATCH (n)-[:ASSIGNS]->(av:Variable)
OPTIONAL MATCH (n)-[:READS]->(rv:Variable)
OPTIONAL MATCH (n)-[:RETURNS]->(ret:Variable)
RETURN collect(DISTINCT {id: av.id, name: av.name, type_hint: av.type_hint, role: 'assigns'}) AS assigns,
       collect(DISTINCT {id: rv.id, name: rv.name, type_hint: rv.type_hint, role: 'reads'}) AS reads,
       collect(DISTINCT {id: ret.id, name: ret.name, type_hint: ret.type_hint, role: 'returns'}) AS returns
"""

# --- Compose: impact analysis for save ---

FIND_CALLERS = """
MATCH (caller:LogicNode)-[:CALLS]->(n:LogicNode {id: $node_id})
WHERE caller.status = 'active'
RETURN caller.id AS id, caller.name AS name
"""
