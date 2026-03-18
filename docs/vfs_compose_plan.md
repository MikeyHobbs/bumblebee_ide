# VFS Compose & Virtual Script — Design Document

## Implementation Status

| Feature | Status |
|---------|--------|
| `/compose/parse` — live parse + graph upsert | Done |
| `/compose/save` — update existing node + impact analysis | Done |
| VFS query prefix (`vfs MATCH ...` in TerminalChat) | Done |
| `/vfs/project-modules` — targeted module projection | Done |
| Suggestion service (deterministic variable matching) | Not yet implemented |
| Script assembly (`/compose/assemble`) | Not yet implemented |

---

> **Vision:** The graph becomes a live, editable surface. Code and graph are two views of the same thing. Users author new logic (Compose Tab) and assemble existing logic (Virtual Script View) through the same editor surface.

---

## Overview

Two workflows that share a single editor surface:

| Workflow | Direction | Description |
|----------|-----------|-------------|
| **Compose** | Bottom-up (code → graph) | Write new functions in Monaco, they become LogicNodes live. Graph suggests compatible functions as you type. |
| **Assemble** | Top-down (graph → code) | Query the graph for a set of functions, auto-assemble a script wiring their inputs/outputs. |

**These are the same tab.** The user sees a single "compose" tab — a writable Monaco editor backed by the graph. Whether you start by typing code or by querying the graph to pre-populate it, you end up in the same editable surface with the same live sync, the same suggestions, and the same save-as-Flow capability. The distinction between "compose" and "virtual script" is an implementation detail of how content arrives in the tab, not a user-visible mode.

---

## Core Principles

1. **Live sync produces the same graph result as batch import.** The compose parse endpoint reuses the same `parse_file()` + `import_file()` pipeline. No separate codepath.

2. **Suggestions are deterministic graph queries.** Variable-aware function matching uses Cypher queries on Variable nodes and LogicNode params/return_type. No LLM for matching.

3. **LLM is the judge, not the inventor.** When assembling scripts, the LLM evaluates compatibility ("you have 3 of 4 variables, this function is usable with XYZ tweak"), highlights gaps, and suggests fixes — but does not fabricate variables or data to fill gaps. The LLM operates on Logic Packs built from the graph.

4. **Graph is source of truth. No file writes on save.** Editing and saving updates the LogicNode in FalkorDB — it does NOT write to the filesystem. VFS projection (graph → `.bumblebee/vfs/` files) is a separate, on-demand operation. The editor is a direct graph surface, not a file editor. This is the core principle of the code-as-data architecture: we break away from the normal filesystem.

5. **Imports via DEPENDS_ON edges.** No explicit `dependencies` field on LogicNode. Resolve imports from edge traversal at generation time.

---

## Architecture

### Tab System

The current editor is single-view, read-only. It must become multi-tab, and **every tab is writable**.

There is one tab kind from the user's perspective. Internally, a tab tracks its origin:

| Origin | URI Scheme | Behavior |
|--------|------------|----------|
| Clicked a graph node | `bumblebee://node/{nodeId}` | Opens existing LogicNode source, editable. On save: updates the LogicNode, runs impact analysis, highlights breaking functions in red. |
| Created new ("+") | `bumblebee://compose/{tabId}` | Empty editor. Live sync creates new LogicNodes as you type. |
| Assembled from query | `bumblebee://compose/{tabId}` | Pre-populated with assembled script. Same live sync + suggestions. |

**Key insight:** There is no read-only mode. When a user opens a node from the graph, they can edit it immediately. Saving triggers impact analysis (via existing `IMPACT_ANALYSIS` Cypher query) and highlights affected downstream functions on the graph canvas. This makes the editor feel like a single unified surface regardless of how you got there.

`openNodeView()` still works — it opens a tab for an existing node, but the tab is now editable.

### Save & Impact Analysis (Existing Nodes)

When a user edits an existing LogicNode and saves:

```
User edits existing function → Cmd+S
      │
      ▼
POST /api/v1/compose/save
      │
      ├── logic_node_service.update_node()  ← recompute hash, re-extract variables
      ├── IMPACT_ANALYSIS query             ← find downstream consumers
      ├── Signature change detection        ← find callers that would break
      │
      ▼
{ updated_node, impacted_nodes: [{ id, name, reason }] }
      │
      ├── WebSocket: graph:updated + node:pulse
      └── Frontend: highlight impacted nodes in red (pulsing, auto-clear)
```

This makes consequences of edits visible immediately. A signature change highlights all callers. A body change that mutates variables highlights all downstream readers.

**Important:** Save writes to the graph only — NOT to the filesystem. VFS projection is a separate on-demand step. The editor is a direct graph manipulation surface.

### Live Parse Pipeline (Compose)

```
User types in Monaco
      │
      ▼ (500ms debounce)
POST /api/v1/compose/parse
      │
      ├── parse_file(source, module_path)     ← same tree-sitter parser
      ├── import_file(module_path, source)    ← same import pipeline
      ├── suggestion_service(variables)       ← new: deterministic graph query
      │
      ▼
{ node_ids, variable_ids, suggestions }
      │
      ├── WebSocket broadcast: graph:updated
      └── Frontend: update compose lens + suggestion panel
```

Compose modules use `__compose__.{tab_id}` as `module_path` to distinguish from imported code.

### Script Assembly Pipeline (Virtual Script)

```
User selects nodes (Cypher query / NL / graph selection)
      │
      ▼
POST /api/v1/compose/assemble
      │
      ├── Fetch each LogicNode
      ├── For methods with self: follow MEMBER_OF → class + __init__
      ├── Query each node's data flow (ASSIGNS/READS/RETURNS)
      ├── Build dependency graph between selected nodes
      ├── Topological sort
      ├── Generate script: imports → class instantiations → wired calls
      ├── Identify gaps: variables needed but not produced
      │
      ▼
{ script, imports, gaps, class_context }
```

### LLM Integration (Planned)

The suggestion service and script assembler provide deterministic results first. The LLM layer sits on top:

1. **Compose suggestions**: After deterministic matching finds candidate functions, the LLM evaluates partial matches — "function X needs 4 params, you have 3, the missing `config` param can be obtained from function Y in the graph."

2. **Script assembly review**: After deterministic assembly, the LLM reviews the wired script and produces a compatibility report — highlighting type mismatches, suggesting reorderings, and recommending additional functions from the graph to fill gaps.

3. **Tool-use interface**: The LLM uses existing agent tools (`find_node`, `get_variable_timeline`, `get_logic_pack`, `run_cypher`) to query the graph. It does not bypass the graph — it operates through it.

This is not v1. The deterministic layer ships first and is useful on its own. The LLM layer is additive.

### Compose Lens (Graph View)

When a compose tab is active, the Atlas graph view applies a lens:

| Node Category | Visual Treatment |
|---------------|-----------------|
| Nodes authored in compose | Bright, highlighted |
| 1-hop neighbors (referenced) | Slightly dimmed but visible |
| Everything else | Faded to near-invisible |

This reuses the existing `nodeReducer`/`edgeReducer` pattern from query result highlighting. A `composeContextNodeIds` set in `graphStore` drives the lens. Clearing the compose tab clears the lens.

### Wider Context for Methods

When a selected method has a `self` parameter:

1. Follow `MEMBER_OF` edge → get the class LogicNode
2. Get the class's `__init__` method → extract constructor params
3. Generate class instantiation in the assembled script

This is the minimum to make method references usable. The goal is to move toward method-level development where classes become less central.

### Variable-Aware Suggestions (Deterministic)

The suggestion service queries the graph for functions whose inputs/outputs match variables in the editor:

1. **Typed variables**: Query `FIND_NODES_BY_PARAM_TYPE` and `FIND_NODES_BY_RETURN_TYPE`
2. **Untyped variables**: Query `FIND_NODES_BY_PARAM_NAME` (fuzzy match)
3. **Ranking**: Exact type match > partial type match > name match
4. **Future**: Batch LLM inference to strongly type and normalize variable names across a codebase (backlog)

### Flows

Virtual scripts are ad-hoc explorations that can be stored as Flows. The existing Flow model supports this:

- Save: `POST /api/v1/flows` with selected `node_ids`, entry/exit points
- Load: Query existing Flows — if a Flow already answers the user's question, no need to rebuild
- Edit: Modify the script, update the Flow
- Promote: When a Flow matures, promote to `flow_function` LogicNode

---

## New Cypher Queries

### Suggestion Queries

```cypher
-- Find LogicNodes whose params include a given type
FIND_NODES_BY_PARAM_TYPE = """
MATCH (n:LogicNode)
WHERE n.status = 'active' AND n.params CONTAINS $type_hint
RETURN n.id, n.name, n.params, n.signature, n.return_type
LIMIT $limit
"""

-- Find LogicNodes returning a given type
FIND_NODES_BY_RETURN_TYPE = """
MATCH (n:LogicNode)
WHERE n.status = 'active' AND n.return_type = $type_hint
RETURN n.id, n.name, n.params, n.signature, n.return_type
LIMIT $limit
"""

-- Find LogicNodes by param name (for untyped variables)
FIND_NODES_BY_PARAM_NAME = """
MATCH (n:LogicNode)
WHERE n.status = 'active' AND n.params CONTAINS $param_name
RETURN n.id, n.name, n.params, n.signature, n.return_type
LIMIT $limit
"""
```

### Assembly Queries

```cypher
-- Get class + __init__ for a method
GET_CLASS_FOR_METHOD = """
MATCH (m:LogicNode {id: $method_id})-[:MEMBER_OF]->(c:LogicNode {kind: 'class'})
OPTIONAL MATCH (init:LogicNode)-[:MEMBER_OF]->(c)
WHERE init.name ENDS WITH '.__init__'
RETURN c.id AS class_id, c.name AS class_name, c.source_text AS class_source,
       init.id AS init_id, init.params AS init_params
"""

-- Get all variables a node assigns/reads/returns
GET_NODE_DATA_FLOW = """
MATCH (n:LogicNode {id: $node_id})
OPTIONAL MATCH (n)-[:ASSIGNS]->(av:Variable)
OPTIONAL MATCH (n)-[:READS]->(rv:Variable)
OPTIONAL MATCH (n)-[:RETURNS]->(ret:Variable)
RETURN collect(DISTINCT {id: av.id, name: av.name, type_hint: av.type_hint, role: 'assigns'}) AS assigns,
       collect(DISTINCT {id: rv.id, name: rv.name, type_hint: rv.type_hint, role: 'reads'}) AS reads,
       collect(DISTINCT {id: ret.id, name: ret.name, type_hint: ret.type_hint, role: 'returns'}) AS returns
"""
```

---

## New API Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/v1/compose/parse` | POST | Live parse + graph upsert + variable suggestions |
| `/api/v1/compose/assemble` | POST | Assemble virtual script from selected node IDs |

### POST /api/v1/compose/parse

```
Body: { source: string, module_path: string }
Response: {
  report: ImportReport,
  node_ids: string[],
  variable_ids: string[],
  suggestions: Suggestion[]
}
```

### POST /api/v1/compose/assemble

```
Body: { node_ids: string[], query_mode: "explore" | "vfs" }
Response: {
  script: string,
  imports: string[],
  gaps: Gap[],
  class_context: ClassContext[]
}
```

`query_mode` controls scope: `"explore"` = full graph, `"vfs"` = only compose-authored nodes.

---

## File Map

### New Files

| File | Purpose |
|------|---------|
| `backend/app/routers/compose.py` | Parse + assemble endpoints |
| `backend/app/services/compose/__init__.py` | Compose service package |
| `backend/app/services/compose/suggestion_service.py` | Variable → function matching (deterministic) |
| `backend/app/services/compose/script_assembler.py` | Multi-node script generation + gap detection |
| `frontend/src/api/compose.ts` | API hooks for compose endpoints |
| `frontend/src/hooks/useComposeSync.ts` | Debounced live parse hook |
| `frontend/src/components/panels/ComposeSuggestionsPanel.tsx` | Suggestion UI panel |

### Modified Files

| File | Change |
|------|--------|
| `frontend/src/store/editorStore.ts` | Single view → multi-tab architecture |
| `frontend/src/components/layout/TabBar.tsx` | History breadcrumb → real tab bar |
| `frontend/src/components/editor/CodeEditor.tsx` | Read-only → conditional read/write by tab kind |
| `frontend/src/editor/ModelManager.ts` | Add compose/vscript model management |
| `frontend/src/store/graphStore.ts` | Add `composeContextNodeIds` + actions |
| `frontend/src/components/canvas/AtlasOverview.tsx` | Compose lens in node/edge reducers |
| `backend/app/graph/logic_queries.py` | 5 new Cypher query templates |
| `backend/app/main.py` | Register compose router |
