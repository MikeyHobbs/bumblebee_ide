# Schema Specification: Bumblebee IDE Graph

This document defines the complete schema for the Bumblebee knowledge graph — node types, edge types, serialization formats, and the `.bumblebee/` directory structure.

---

## 1. Graph Node Types

### 1.1 LogicNode (Tier 1)

The atomic unit of logic. Authored by agents and humans.

**FalkorDB Label:** `LogicNode`

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | `string (UUID7)` | Yes | Stable primary key. Time-sortable. Edges reference this — never changes on edit. |
| `ast_hash` | `string (SHA-256)` | Yes | Hash of canonical AST. Used for deduplication detection, not identity. |
| `kind` | `enum` | Yes | One of: `function`, `method`, `class`, `constant`, `type_alias`, `flow_function` |
| `name` | `string` | Yes | Qualified name (e.g., `AuthService.verify_token`) |
| `module_path` | `string` | Yes | Logical module path (e.g., `app.services.auth`) |
| `signature` | `string` | Yes | Full signature text (e.g., `def verify_token(token: str) -> bool`) |
| `source_text` | `string` | Yes | Complete source code of the node |
| `semantic_intent` | `string` | No | One-line natural language description of what the node does |
| `docstring` | `string` | No | Extracted docstring, if present |
| `decorators` | `list[string]` | No | Decorator names (e.g., `["staticmethod", "override"]`) |
| `params` | `list[ParamSpec]` | No | Parameter specifications (functions/methods only) |
| `return_type` | `string` | No | Return type annotation, if present |
| `tags` | `list[string]` | No | User/agent-defined tags for categorization |
| `class_id` | `string (UUID7)` | No | Parent class UUID (methods only). Also captured via `MEMBER_OF` edge. |
| `derived_from` | `string (UUID7)` | No | UUID of the node this was forked from, if any |
| `start_line` | `int` | No | Line number in the projected VFS file |
| `end_line` | `int` | No | End line number in the projected VFS file |
| `status` | `enum` | Yes | One of: `active`, `deprecated`. Default: `active` |
| `created_at` | `datetime (ISO 8601)` | Yes | When the node was first created |
| `updated_at` | `datetime (ISO 8601)` | Yes | When the node was last modified |

**ParamSpec structure:**

```json
{
  "name": "token",
  "type_hint": "str",
  "default": null,
  "kind": "positional_or_keyword"
}
```

`kind` is one of: `positional_only`, `positional_or_keyword`, `keyword_only`, `var_positional` (`*args`), `var_keyword` (`**kwargs`).

### 1.2 Variable (Tier 2)

The atomic unit of data flow. Derived from LogicNode analysis.

**FalkorDB Label:** `Variable`

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | `string (UUID7)` | Yes | Stable primary key |
| `name` | `string` | Yes | Variable name (e.g., `token`, `self.config`) |
| `scope` | `string` | Yes | Fully qualified scope (e.g., `app.services.auth.AuthService.verify_token.token`) |
| `origin_node_id` | `string (UUID7)` | Yes | UUID of the LogicNode where this variable is first assigned |
| `origin_line` | `int` | No | Line number of first assignment |
| `type_hint` | `string` | No | Type annotation, if present (e.g., `str`, `list[int]`) |
| `is_parameter` | `bool` | Yes | True if this variable is a function parameter |
| `is_attribute` | `bool` | Yes | True if this is an instance/class attribute (e.g., `self.x`) |
| `created_at` | `datetime (ISO 8601)` | Yes | When the variable node was created |

### 1.3 TypeShape (Tier 1.5)

A structural type descriptor inferred from usage evidence. TypeShape is a hub node — variables and functions link to it, turning type compatibility from O(n*m) property comparison into O(1) graph traversal.

**FalkorDB Label:** `TypeShape`

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | `string (UUID5)` | Yes | Deterministic from `shape_hash` (namespace UUID5) |
| `shape_hash` | `string (SHA-256)` | Yes | Hash of the canonical `definition` JSON |
| `kind` | `enum` | Yes | One of: `primitive`, `generic`, `structural`, `hint` |
| `base_type` | `string` | No | Base type name (e.g., `list`, `dict`, `str`) |
| `definition` | `string (JSON)` | Yes | Canonical JSON describing the shape structure |
| `created_at` | `datetime (ISO 8601)` | Yes | When the shape was first created |

**Shape inference:** Shapes are inferred from usage evidence (attribute access, subscript access, method calls) rather than relying solely on type annotations. Variables with no evidence get no TypeShape.

### 1.4 Flow

A named, curated end-to-end process through the graph.

**FalkorDB Label:** `Flow`

| Property | Type | Required | Description |
|----------|------|----------|-------------|
| `id` | `string (UUID7)` | Yes | Stable primary key |
| `name` | `string` | Yes | Human-readable name (e.g., `order_processing`) |
| `description` | `string` | No | What this flow represents |
| `entry_point` | `string (UUID7)` | Yes | UUID of the LogicNode where the flow starts |
| `exit_points` | `list[string (UUID7)]` | No | UUIDs of LogicNodes where the flow terminates |
| `node_ids` | `list[string (UUID7)]` | Yes | Ordered list of LogicNode UUIDs in the flow |
| `sub_flow_ids` | `list[string (UUID7)]` | No | UUIDs of child Flows contained in this flow |
| `parent_flow_id` | `string (UUID7)` | No | UUID of the parent Flow, if this is a sub-flow |
| `promoted_node_id` | `string (UUID7)` | No | UUID of the LogicNode created when this flow is promoted to a flow_function |
| `created_at` | `datetime (ISO 8601)` | Yes | When the flow was defined |
| `updated_at` | `datetime (ISO 8601)` | Yes | When the flow was last modified |

---

## 2. Edge Types

### 2.1 LogicNode → LogicNode Edges

| Edge Type | From | To | Properties | Description |
|-----------|------|----|------------|-------------|
| `CALLS` | LogicNode | LogicNode | `call_line`, `call_order`, `arg_count` | Function invocation |
| `DEPENDS_ON` | LogicNode | LogicNode | `dependency_kind` | Structural dependency (import, type reference) |
| `IMPLEMENTS` | LogicNode | LogicNode | — | Interface/protocol implementation |
| `VALIDATES` | LogicNode | LogicNode | `validation_kind` | Input validation relationship |
| `TRANSFORMS` | LogicNode | LogicNode | `transform_kind` | Data transformation pipeline step |
| `INHERITS` | LogicNode (class) | LogicNode (class) | `order` | Class inheritance. `order` = MRO position. |
| `MEMBER_OF` | LogicNode (method) | LogicNode (class) | `access` | Class membership. `access` = `public`, `protected`, `private` |

### 2.2 LogicNode → Variable Edges

| Edge Type | From | To | Properties | Description |
|-----------|------|----|------------|-------------|
| `ASSIGNS` | LogicNode | Variable | `line`, `is_rebind` | Variable creation or re-binding |
| `MUTATES` | LogicNode | Variable | `line`, `mutation_kind` | In-place state change |
| `READS` | LogicNode | Variable | `line` | Read-only access |
| `RETURNS` | LogicNode | Variable | `line` | Return/yield value |

`mutation_kind` is one of: `method_call`, `subscript_assign`, `attr_assign`, `augmented_assign`.

### 2.3 Variable → Variable Edges

| Edge Type | From | To | Properties | Description |
|-----------|------|----|------------|-------------|
| `PASSES_TO` | Variable | Variable | `call_line`, `arg_position`, `arg_keyword` | Argument passing across call boundary |
| `FEEDS` | Variable | Variable | `line`, `expression_text`, `via` | Intra-function data dependency |

`via` is one of: `assignment`, `mutation_arg`, `call_arg`, `call_return`.

### 2.4 TypeShape Edges

| Edge Type | From | To | Properties | Description |
|-----------|------|----|------------|-------------|
| `HAS_SHAPE` | Variable | TypeShape | — | Variable has this structural shape |
| `ACCEPTS` | LogicNode | TypeShape | `param_name` | Function parameter requires this shape |
| `PRODUCES` | LogicNode | TypeShape | — | Function returns this shape |
| `COMPATIBLE_WITH` | TypeShape | TypeShape | — | Source shape is a superset of target shape |

### 2.5 Flow Edges

| Edge Type | From | To | Properties | Description |
|-----------|------|----|------------|-------------|
| `STEP_OF` | LogicNode | Flow | `step_order` | LogicNode participates in a flow at this position |
| `CONTAINS_FLOW` | Flow | Flow | `step_order` | Parent flow contains a sub-flow at this position |
| `PROMOTED_TO` | Flow | LogicNode | — | Flow was promoted to a callable flow_function LogicNode |

---

## 3. Hash Identity System

### 3.1 AST Hash Computation

The `ast_hash` is a SHA-256 digest of the **canonical AST** of the LogicNode's source text.

**Canonicalization rules:**
1. Parse source text with tree-sitter.
2. Strip comments and docstrings.
3. Normalize whitespace (single space between tokens, no trailing whitespace).
4. Sort decorator list alphabetically.
5. Serialize the normalized AST to a deterministic string representation.
6. Compute SHA-256 of the UTF-8 encoded string.

**Purpose:** Deduplication detection only. Two nodes with the same `ast_hash` contain identical logic. The system warns on duplicate creation but does not prevent it (the same logic may intentionally exist in multiple contexts).

### 3.2 Node Identity Rules

| Scenario | Action | Identity |
|----------|--------|----------|
| Body logic changes (refactor, bug fix) | `update_node(id)` | Same UUID, new `ast_hash` |
| Signature changes (params, return type) | System prompts: "Create new or update?" | Agent decides |
| New node from scratch | `create_node(...)` | New UUID |
| Fork from existing | `create_node(derived_from=existing_id)` | New UUID, `derived_from` set |
| Duplicate logic detected | System warns | Agent decides to reuse or proceed |

---

## 4. Git Serialization Format

### 4.1 Directory Structure

```
project/
  .bumblebee/
    meta.json
    nodes/
      <uuid>.json
      <uuid>.json
      ...
    variables/
      var_<scope_hash>.json
      ...
    edges/
      manifest.json
    flows/
      flow_<name>.json
      ...
    type_shapes/
      <shape_hash>.json
      ...
    vfs/                    # GIT-TRACKED — editable projections
      services/
        auth.py             #   edits sync back to graph
      models/
        user.py
```

### 4.2 `meta.json`

```json
{
  "version": "1.0.0",
  "schema_version": 1,
  "graph_name": "bumblebee",
  "node_count": 342,
  "variable_count": 1205,
  "edge_count": 4521,
  "flow_count": 8,
  "last_serialized": "2026-03-17T10:30:00Z",
  "source_language": "python",
  "source_root": "/absolute/path/to/original/repo"
}
```

### 4.3 LogicNode File (`nodes/<uuid>.json`)

```json
{
  "id": "019537d5-a1b2-7def-8c90-1234567890ab",
  "ast_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
  "kind": "method",
  "name": "AuthService.verify_token",
  "module_path": "app.services.auth",
  "signature": "def verify_token(self, token: str) -> bool",
  "source_text": "def verify_token(self, token: str) -> bool:\n    \"\"\"Verify a JWT token and return validity.\"\"\"\n    try:\n        payload = jwt.decode(token, self.secret_key, algorithms=[\"HS256\"])\n        return payload.get(\"exp\", 0) > time.time()\n    except jwt.InvalidTokenError:\n        return False",
  "semantic_intent": "Validates a JWT token by decoding it and checking expiration",
  "docstring": "Verify a JWT token and return validity.",
  "decorators": [],
  "params": [
    { "name": "self", "type_hint": null, "default": null, "kind": "positional_or_keyword" },
    { "name": "token", "type_hint": "str", "default": null, "kind": "positional_or_keyword" }
  ],
  "return_type": "bool",
  "tags": ["auth", "security", "jwt"],
  "class_id": "019537d5-b2c3-7def-8c90-abcdef012345",
  "derived_from": null,
  "status": "active",
  "created_at": "2026-03-15T14:22:00Z",
  "updated_at": "2026-03-17T09:15:00Z"
}
```

### 4.4 Variable File (`variables/var_<scope_hash>.json`)

Variables are grouped by scope to keep related variables together. The `<scope_hash>` is a truncated SHA-256 of the scope string.

```json
{
  "scope": "app.services.auth.AuthService.verify_token",
  "scope_hash": "a1b2c3d4",
  "variables": [
    {
      "id": "019537d5-c3d4-7def-8c90-variable00001",
      "name": "token",
      "scope": "app.services.auth.AuthService.verify_token.token",
      "origin_node_id": "019537d5-a1b2-7def-8c90-1234567890ab",
      "origin_line": 1,
      "type_hint": "str",
      "is_parameter": true,
      "is_attribute": false,
      "created_at": "2026-03-15T14:22:00Z"
    },
    {
      "id": "019537d5-c3d4-7def-8c90-variable00002",
      "name": "payload",
      "scope": "app.services.auth.AuthService.verify_token.payload",
      "origin_node_id": "019537d5-a1b2-7def-8c90-1234567890ab",
      "origin_line": 4,
      "type_hint": null,
      "is_parameter": false,
      "is_attribute": false,
      "created_at": "2026-03-15T14:22:00Z"
    }
  ]
}
```

### 4.5 Edge Manifest (`edges/manifest.json`)

```json
{
  "schema_version": 1,
  "edge_count": 4521,
  "edges": [
    {
      "type": "CALLS",
      "source": "019537d5-a1b2-7def-8c90-1234567890ab",
      "target": "019537d5-d4e5-7def-8c90-9876543210fe",
      "properties": {
        "call_line": 4,
        "call_order": 0,
        "arg_count": 3
      }
    },
    {
      "type": "ASSIGNS",
      "source": "019537d5-a1b2-7def-8c90-1234567890ab",
      "target": "019537d5-c3d4-7def-8c90-variable00002",
      "properties": {
        "line": 4,
        "is_rebind": false
      }
    },
    {
      "type": "PASSES_TO",
      "source": "019537d5-c3d4-7def-8c90-variable00001",
      "target": "019537d5-e5f6-7def-8c90-variable00099",
      "properties": {
        "call_line": 4,
        "arg_position": 0,
        "arg_keyword": null
      }
    },
    {
      "type": "MEMBER_OF",
      "source": "019537d5-a1b2-7def-8c90-1234567890ab",
      "target": "019537d5-b2c3-7def-8c90-abcdef012345",
      "properties": {
        "access": "public"
      }
    }
  ]
}
```

**Sharding strategy:** If `manifest.json` exceeds ~10MB, shard by edge type into separate files: `edges/calls.json`, `edges/assigns.json`, etc. The system auto-detects whether the edges directory contains a single manifest or per-type files.

### 4.6 Flow File (`flows/flow_<name>.json`)

```json
{
  "id": "019537d5-f6a7-7def-8c90-flow000000001",
  "name": "order_processing",
  "description": "End-to-end order processing from cart checkout to fulfillment",
  "entry_point": "019537d5-0001-7def-8c90-entrypoint001",
  "exit_points": [
    "019537d5-0099-7def-8c90-exitpoint0001",
    "019537d5-0099-7def-8c90-exitpoint0002"
  ],
  "node_ids": [
    "019537d5-0001-7def-8c90-entrypoint001",
    "019537d5-0002-7def-8c90-step00000002",
    "019537d5-0003-7def-8c90-step00000003",
    "019537d5-0099-7def-8c90-exitpoint0001",
    "019537d5-0099-7def-8c90-exitpoint0002"
  ],
  "sub_flow_ids": [
    "019537d5-f6a7-7def-8c90-subflow000001",
    "019537d5-f6a7-7def-8c90-subflow000002"
  ],
  "parent_flow_id": null,
  "promoted_node_id": null,
  "created_at": "2026-03-16T08:00:00Z",
  "updated_at": "2026-03-17T10:00:00Z"
}
```

---

## 5. FalkorDB Index Definitions

```cypher
-- Primary lookups
CREATE INDEX FOR (n:LogicNode) ON (n.id)
CREATE INDEX FOR (n:LogicNode) ON (n.ast_hash)
CREATE INDEX FOR (n:LogicNode) ON (n.name)
CREATE INDEX FOR (n:LogicNode) ON (n.kind)
CREATE INDEX FOR (n:LogicNode) ON (n.module_path)
CREATE INDEX FOR (n:LogicNode) ON (n.status)

CREATE INDEX FOR (v:Variable) ON (v.id)
CREATE INDEX FOR (v:Variable) ON (v.name)
CREATE INDEX FOR (v:Variable) ON (v.scope)
CREATE INDEX FOR (v:Variable) ON (v.origin_node_id)

CREATE INDEX FOR (t:TypeShape) ON (t.id)
CREATE INDEX FOR (t:TypeShape) ON (t.shape_hash)

CREATE INDEX FOR (f:Flow) ON (f.id)
CREATE INDEX FOR (f:Flow) ON (f.name)
CREATE INDEX FOR (f:Flow) ON (f.parent_flow_id)
```

---

## 6. Key Cypher Query Patterns

### 6.1 Mutation Timeline Query

```cypher
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
```

### 6.2 Dependency Subgraph (Logic Pack)

```cypher
MATCH (root:LogicNode {id: $node_id})
CALL {
  WITH root
  MATCH path = (root)-[:CALLS|DEPENDS_ON*1..$depth]->(dep:LogicNode)
  RETURN dep, relationships(path) as rels
}
RETURN root, collect(DISTINCT dep) as dependencies, collect(rels) as edges
```

### 6.3 Deduplication Check

```cypher
MATCH (existing:LogicNode {ast_hash: $hash, status: 'active'})
WHERE existing.id <> $current_id
RETURN existing.id, existing.name, existing.module_path
```

### 6.4 Impact Analysis

```cypher
MATCH (changed:LogicNode {id: $node_id})-[:MUTATES]->(v:Variable)
MATCH (consumer:LogicNode)-[:READS]->(v)
WHERE consumer.id <> changed.id
RETURN v.name as variable, collect(DISTINCT consumer.name) as affected_consumers
```

### 6.5 Flow Traversal

```cypher
MATCH (f:Flow {id: $flow_id})
MATCH (n:LogicNode)-[s:STEP_OF]->(f)
WITH f, n, s ORDER BY s.step_order
OPTIONAL MATCH (n)-[e:CALLS|DEPENDS_ON|TRANSFORMS]->(next:LogicNode)
WHERE next.id IN f.node_ids
OPTIONAL MATCH (f)-[cf:CONTAINS_FLOW]->(sub:Flow)
RETURN collect(DISTINCT {node: n, step: s.step_order}) as steps,
       collect(DISTINCT {edge: e, from: n.id, to: next.id}) as connections,
       collect(DISTINCT {sub_flow: sub, order: cf.step_order}) as sub_flows
```

### 6.6 Flow Hierarchy (Recursive)

```cypher
MATCH (root:Flow {id: $flow_id})
CALL {
  WITH root
  MATCH path = (root)-[:CONTAINS_FLOW*1..5]->(descendant:Flow)
  RETURN descendant, length(path) as depth, relationships(path) as rels
}
RETURN root, collect({flow: descendant, depth: depth}) as hierarchy
```

### 6.7 Find LogicNodes by Parameter Type (Compose Suggestions)

```cypher
MATCH (n:LogicNode)
WHERE n.status = 'active' AND n.params CONTAINS $type_hint
RETURN n.id, n.name, n.params, n.signature, n.return_type
LIMIT $limit
```

Note: `CONTAINS` on the JSON `params` string is a fast pre-filter. Python-side code parses the JSON for precise matching.

### 6.8 Find LogicNodes by Return Type (Compose Suggestions)

```cypher
MATCH (n:LogicNode)
WHERE n.status = 'active' AND n.return_type = $type_hint
RETURN n.id, n.name, n.params, n.signature, n.return_type
LIMIT $limit
```

### 6.9 Get Class Context for Method (Script Assembly)

```cypher
MATCH (m:LogicNode {id: $method_id})-[:MEMBER_OF]->(c:LogicNode {kind: 'class'})
OPTIONAL MATCH (init:LogicNode)-[:MEMBER_OF]->(c)
WHERE init.name ENDS WITH '.__init__'
RETURN c.id AS class_id, c.name AS class_name, c.source_text AS class_source,
       init.id AS init_id, init.params AS init_params
```

### 6.10 Get Node Data Flow (Script Assembly)

```cypher
MATCH (n:LogicNode {id: $node_id})
OPTIONAL MATCH (n)-[:ASSIGNS]->(av:Variable)
OPTIONAL MATCH (n)-[:READS]->(rv:Variable)
OPTIONAL MATCH (n)-[:RETURNS]->(ret:Variable)
RETURN collect(DISTINCT {id: av.id, name: av.name, type_hint: av.type_hint, role: 'assigns'}) AS assigns,
       collect(DISTINCT {id: rv.id, name: rv.name, type_hint: rv.type_hint, role: 'reads'}) AS reads,
       collect(DISTINCT {id: ret.id, name: ret.name, type_hint: ret.type_hint, role: 'returns'}) AS returns
```
