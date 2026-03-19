# Ticket Backlog: Bumblebee IDE — Code-as-Data Refactor (800-Series)

> **Core principle:** Code lives in the graph as atomic LogicNodes. Files are projections. Git stores the serialized graph. The graph is the source of truth, optimized for AI agent interaction.

---

## Phase 0: Foundation (Hash Identity + Schema) — DONE

### TICKET-800: Hash-Based Identity System — DONE

**File:** `backend/app/services/hash_identity.py`

**Goal:** Implement the dual-identity system: stable UUID7 primary keys + SHA-256 AST hash for deduplication.

**Tasks:**
- Implement `generate_node_id() -> str` using UUID7 (time-sortable).
- Implement `compute_ast_hash(source_text: str) -> str` using tree-sitter canonicalization + SHA-256.
- Canonicalization rules: strip comments/docstrings, normalize whitespace, sort decorators alphabetically, serialize to deterministic string.
- Implement `check_duplicate(ast_hash: str) -> LogicNode | None` that queries FalkorDB for existing nodes with matching hash.
- Implement `detect_signature_change(old_node: LogicNode, new_source: str) -> bool` that compares parameter names/types and return type.

**Acceptance Criteria:**
- `compute_ast_hash` produces identical hashes for semantically identical code with different formatting/comments.
- `compute_ast_hash` produces different hashes for code with different logic.
- `check_duplicate` returns the existing node when a hash collision is found.
- `detect_signature_change` correctly identifies when parameters or return type change.
- UUID7 values are time-sortable and globally unique.

---

### TICKET-801: FalkorDB Schema + Cypher Queries — DONE

**File:** `backend/app/graph/queries.py` (rewrite)

**Goal:** Define the new graph schema (LogicNode, Variable, Flow labels) and implement all core Cypher query templates.

**Tasks:**
- Define index creation queries per `spec.schema.md` Section 5.
- Implement MERGE/CREATE templates for LogicNode, Variable, and Flow nodes.
- Implement edge creation templates for all 14 edge types (CALLS, DEPENDS_ON, IMPLEMENTS, VALIDATES, TRANSFORMS, INHERITS, MEMBER_OF, ASSIGNS, MUTATES, READS, RETURNS, PASSES_TO, FEEDS, STEP_OF).
- Implement the mutation timeline query (spec.schema.md Section 6.1).
- Implement the dependency subgraph query (spec.schema.md Section 6.2).
- Implement the deduplication check query (spec.schema.md Section 6.3).
- Implement the impact analysis query (spec.schema.md Section 6.4).
- Implement the flow traversal query (spec.schema.md Section 6.5).
- Implement node deletion (soft delete: set `status = 'deprecated'`).

**Acceptance Criteria:**
- All indexes are created on graph initialization.
- MERGE operations are idempotent — running the same create twice does not duplicate nodes.
- All query templates are parameterized (no string interpolation of user input).
- Mutation timeline query returns correct results for a variable that spans 3+ LogicNodes.

---

### TICKET-802: Pydantic Models for LogicNode, Variable, Edge, Flow — DONE

**File:** `backend/app/models/logic_models.py`

**Goal:** Define strict Pydantic models matching the schema spec for API serialization and validation.

**Tasks:**
- `LogicNodeCreate` — input model for creating a LogicNode (name, kind, source_text, semantic_intent, tags, derived_from).
- `LogicNodeResponse` — output model with all properties including computed fields (id, ast_hash, created_at, updated_at).
- `LogicNodeUpdate` — input model for updating (new_source_text, semantic_intent, tags).
- `VariableResponse` — output model for Variable nodes.
- `EdgeCreate` — input model (source_id, target_id, edge_type, properties).
- `EdgeResponse` — output model.
- `FlowCreate` — input model (name, description, node_ids, entry_point, exit_points, sub_flow_ids, parent_flow_id).
- `FlowResponse` — output model (includes sub_flow_ids, parent_flow_id, promoted_node_id).
- `FlowHierarchy` — recursive response model for flow hierarchy queries.
- `MutationTimeline` — response model for the timeline query (origin, mutations, reads, passes, feeds, terminal).
- `LogicPack` — response model (nodes, edges, snippets).
- `ParamSpec` — embedded model for function parameters.
- `GapReport` — response model for gap analysis (dead_ends, orphans, missing_error_handling, circular_deps).
- All models use `kind` enums: `LogicNodeKind` (`function`, `method`, `class`, `constant`, `type_alias`, `flow_function`), `EdgeType`, `MutationKind`, `ParamKind`.

**Acceptance Criteria:**
- All models validate correctly with example data from `spec.schema.md`.
- Enum validation rejects invalid `kind` and `edge_type` values.
- `LogicNodeCreate` auto-generates `id` and `ast_hash` via validators.
- All datetime fields use ISO 8601 format.
- Models are JSON-serializable for API responses and Git serialization.

---

## Phase 1: Core Graph Operations — DONE

### TICKET-810: Logic Node CRUD Service — DONE

**File:** `backend/app/services/logic_node_service.py`

**Goal:** Implement create, read, update, deprecate operations for LogicNodes with automatic Variable extraction.

**Tasks:**
- `create_node(data: LogicNodeCreate) -> LogicNodeResponse`:
  - Generate UUID7, compute AST hash, check for duplicates (warn if found).
  - Write LogicNode to FalkorDB.
  - Auto-run variable extraction: parse source_text with tree-sitter, extract Variable nodes + ASSIGNS/MUTATES/READS/RETURNS edges (reuse `variable_extractor.py` logic).
  - Auto-run dataflow extraction: extract PASSES_TO + FEEDS edges (reuse `dataflow_extractor.py` logic).
  - If `kind == "method"` and `class_id` is provided, create MEMBER_OF edge.
- `get_node(node_id: str) -> LogicNodeResponse`: Fetch by UUID with all properties.
- `find_nodes(query: str, kind: str | None, limit: int) -> list[LogicNodeResponse]`: Search by name, tag, or semantic intent.
- `update_node(node_id: str, data: LogicNodeUpdate) -> LogicNodeResponse`:
  - Recompute AST hash. If signature changed, prompt/warn.
  - Update node in-place (same UUID). Edges remain stable.
  - Re-extract all Variable nodes and data-flow edges for this LogicNode (delete old, create new).
- `deprecate_node(node_id: str, replacement_id: str | None) -> None`:
  - Set `status = 'deprecated'`. Optionally link to replacement node.
  - Do NOT delete edges — they serve as historical record.

**Acceptance Criteria:**
- Creating a LogicNode with a function that assigns 3 variables produces 3 Variable nodes and 3 ASSIGNS edges automatically.
- Updating a LogicNode's source_text re-extracts variables — old variable nodes for this LogicNode are replaced.
- Duplicate AST hash triggers a warning (returned in response metadata), not an error.
- Deprecated nodes are excluded from default queries but remain in the graph.

---

### TICKET-811: Edge Service — DONE

**File:** `backend/app/services/edge_service.py`

**Goal:** Implement CRUD operations for edges between nodes.

**Tasks:**
- `add_edge(data: EdgeCreate) -> EdgeResponse`: Validate source and target exist, create typed edge with properties.
- `remove_edge(source_id: str, target_id: str, edge_type: str) -> None`: Delete edge.
- `get_edges(node_id: str, direction: str, edge_types: list[str] | None) -> list[EdgeResponse]`:
  - `direction` is `outgoing`, `incoming`, or `both`.
  - Optional filter by edge type.
- `get_dependencies(node_id: str, depth: int, edge_types: list[str] | None) -> list[EdgeResponse]`: Multi-hop outgoing traversal.
- `get_dependents(node_id: str, depth: int) -> list[EdgeResponse]`: Multi-hop incoming traversal.

**Acceptance Criteria:**
- Adding an edge with an invalid source/target UUID returns a 404 error.
- Adding a duplicate edge (same source, target, type) is idempotent.
- Multi-hop traversal with `depth=3` returns edges up to 3 hops away.
- Edge type filtering works correctly (e.g., only CALLS edges).

---

### TICKET-812: Variable Timeline Service — DONE

**File:** `backend/app/services/variable_timeline_service.py`

**Goal:** Implement the mutation timeline query and variable tracing.

**Tasks:**
- `get_variable_timeline(variable_id: str) -> MutationTimeline`:
  - Execute the mutation timeline Cypher query (spec.schema.md Section 6.1).
  - Return structured response: origin LogicNode + ASSIGNS edge, list of MUTATES edges with their LogicNodes, list of READS edges, PASSES_TO chains, FEEDS edges, terminal node (last consumer).
- `trace_variable(name: str, scope: str | None) -> list[MutationTimeline]`:
  - Find Variable nodes matching name (optionally scoped).
  - Return mutation timeline for each match.
- `get_impact(node_id: str) -> list[dict]`:
  - For a LogicNode, find all variables it MUTATES, then find all LogicNodes that READ those variables.
  - Return: `[{variable: str, affected_consumers: [str]}]`.

**Acceptance Criteria:**
- Timeline for a variable that passes through 5 functions via PASSES_TO returns the complete chain.
- `trace_variable("config")` returns timelines for all variables named `config` across all scopes.
- Impact analysis correctly identifies downstream readers 3+ hops away via PASSES_TO chains.
- All queries execute in < 100ms on a graph with 50k+ nodes.

---

### TICKET-813: REST API Endpoints — DONE

**File:** `backend/app/routers/logic_nodes.py`, `backend/app/routers/edges.py`, `backend/app/routers/variables.py`

**Goal:** Expose all Phase 0-1 services as REST endpoints.

**Tasks:**
- **LogicNode endpoints:**
  - `POST /api/v1/nodes` — Create a LogicNode
  - `GET /api/v1/nodes/{node_id}` — Get a LogicNode by UUID
  - `GET /api/v1/nodes` — Search/list nodes (`?query=`, `?kind=`, `?limit=`)
  - `PATCH /api/v1/nodes/{node_id}` — Update a LogicNode
  - `DELETE /api/v1/nodes/{node_id}` — Deprecate a LogicNode (`?replacement_id=`)
  - `GET /api/v1/nodes/{node_id}/logic-pack` — Get Logic Pack subgraph (`?hops=`, `?edge_types=`)
- **Edge endpoints:**
  - `POST /api/v1/edges` — Add an edge
  - `DELETE /api/v1/edges` — Remove an edge (`?source=`, `?target=`, `?type=`)
  - `GET /api/v1/nodes/{node_id}/edges` — Get edges for a node (`?direction=`, `?types=`)
  - `GET /api/v1/nodes/{node_id}/dependencies` — Get dependency subgraph (`?depth=`, `?edge_types=`)
  - `GET /api/v1/nodes/{node_id}/dependents` — Get dependent subgraph (`?depth=`)
- **Variable endpoints:**
  - `GET /api/v1/variables/{variable_id}/timeline` — Mutation timeline
  - `GET /api/v1/variables/search` — Search variables (`?name=`, `?scope=`)
  - `GET /api/v1/variables/trace` — Trace a variable (`?name=`, `?scope=`)
  - `GET /api/v1/nodes/{node_id}/impact` — Impact analysis
- **Utility endpoints:**
  - `POST /api/v1/query` — Raw Cypher query (`{ "cypher": "...", "params": {} }`)
  - `POST /api/v1/nodes/{node_id}/vfs` — Project VFS for a node (`?format=python`)

**Acceptance Criteria:**
- All endpoints return proper HTTP status codes (201 for create, 200 for get/update, 204 for delete, 404 for not found, 422 for validation errors).
- All endpoints are documented with OpenAPI schemas (auto-generated from Pydantic models).
- Pagination works on list endpoints (`?offset=`, `?limit=`).
- Raw Cypher endpoint validates query syntax before execution.

---

## Phase 2: Serialization (Graph-to-Git) — DONE

### TICKET-820: Graph-to-Git Serializer — DONE

**File:** `backend/app/services/serializer.py`

**Goal:** Serialize the full FalkorDB graph state to the `.bumblebee/` directory structure.

**Tasks:**
- Implement `serialize_graph(output_dir: str) -> SerializationReport`:
  - Write `meta.json` with counts and timestamp.
  - Write each LogicNode as `nodes/<uuid>.json`.
  - Write Variable nodes grouped by scope as `variables/var_<scope_hash>.json`.
  - Write all edges as `edges/manifest.json`.
  - Write each Flow as `flows/flow_<name>.json`.
- Implement incremental serialization: only write files for nodes/edges that changed since last serialization (track via `updated_at` comparison).
- JSON formatting: 2-space indent, sorted keys, for clean Git diffs.

**Acceptance Criteria:**
- Full serialization of a 500-node graph completes in < 2 seconds.
- Incremental serialization of 5 changed nodes completes in < 200ms.
- Output matches the format in `spec.schema.md` Section 4.
- Running serialization twice without changes produces zero Git diff.

---

### TICKET-821: Git-to-Graph Deserializer — DONE

**File:** `backend/app/services/deserializer.py`

**Goal:** Load a `.bumblebee/` directory into FalkorDB on startup.

**Tasks:**
- Implement `deserialize_graph(input_dir: str) -> DeserializationReport`:
  - Read `meta.json` for validation.
  - Load all `nodes/*.json` files, create LogicNode nodes in FalkorDB.
  - Load all `variables/var_*.json` files, create Variable nodes.
  - Load `edges/manifest.json` (or per-type files if sharded), create all edges.
  - Load all `flows/flow_*.json` files, create Flow nodes + STEP_OF edges.
- Implement conflict detection: if FalkorDB already has data, compare and report differences.
- Implement merge strategy: option to replace (clear graph first) or merge (skip existing, add new).

**Acceptance Criteria:**
- Deserializing a serialized graph produces an identical graph (round-trip test).
- Loading a 500-node graph from JSON files completes in < 5 seconds.
- Conflict detection correctly identifies nodes that exist in both graph and files with different content.

---

### TICKET-822: Semantic Diff Engine — DONE

**File:** `backend/app/services/semantic_diff.py`

**Goal:** Compute meaningful diffs between two graph states.

**Tasks:**
- Implement `compute_diff(old_dir: str, new_dir: str) -> SemanticDiff`:
  - Compare node sets: added, removed (deprecated), modified (same UUID, different hash).
  - Compare edge sets: added, removed.
  - Compare variable sets: added, removed, modified.
  - For modified nodes: include old and new `source_text`, `signature`, `semantic_intent`.
- Implement `compute_diff_from_graph(serialized_dir: str) -> SemanticDiff`:
  - Compare the serialized files against the live FalkorDB state.
- Return structured report suitable for frontend visualization.

**Acceptance Criteria:**
- Renaming a function's body (same UUID) shows as "modified" with old/new source.
- Adding a new LogicNode shows as "added" with all its auto-extracted variables and edges.
- Deprecating a node shows as "removed" with a list of affected edges.
- Diff computation completes in < 1 second for 1000-node graphs.

---

### TICKET-823: File Watcher for `.bumblebee/` Directory — DONE

**File:** `backend/app/services/bumblebee_watcher.py`

**Goal:** Watch the `.bumblebee/` directory for external changes (e.g., `git pull`) and sync to FalkorDB.

**Tasks:**
- Implement a watchdog observer on `.bumblebee/nodes/`, `.bumblebee/variables/`, `.bumblebee/edges/`, `.bumblebee/flows/`.
- On file change: deserialize the changed file(s) and update FalkorDB.
- Debounce rapid changes (300ms) for `git checkout` operations that modify many files.
- Emit `graph:updated` WebSocket event after sync.
- Ignore changes to `.bumblebee/vfs/` (gitignored, output only).

**Acceptance Criteria:**
- After `git pull` that modifies `.bumblebee/nodes/xyz.json`, the corresponding LogicNode in FalkorDB is updated within 1 second.
- Rapid file changes (e.g., `git checkout` modifying 50 files) are batched into a single sync operation.
- VFS directory changes do not trigger sync.

---

## Phase 3: Import Pipeline — DONE

### TICKET-830: Python-to-LogicNode Converter — DONE

**File:** `backend/app/services/import_pipeline.py`

**Goal:** Convert existing Python source files into LogicNodes in the graph.

**Tasks:**
- Implement `import_file(file_path: str) -> ImportReport`:
  - Parse with tree-sitter (reuse existing `ast_parser.py`).
  - For each function/method: create a LogicNode with `kind=function/method`, extract source_text, signature, params, return_type, decorators, docstring.
  - For each class: create a LogicNode with `kind=class`, create MEMBER_OF edges for methods, INHERITS edges for base classes.
  - For each top-level constant/type alias: create LogicNode with appropriate `kind`.
  - Run relationship extraction (reuse `relationship_extractor.py`): create CALLS, DEPENDS_ON edges.
  - Auto-extract variables and data-flow edges (via logic_node_service create pipeline).
- Implement `import_directory(dir_path: str, patterns: list[str]) -> ImportReport`:
  - Recursively import all matching files.
  - Track progress, emit WebSocket events.
- Implement `import_incremental(file_path: str) -> ImportReport`:
  - Compare file checksum to existing LogicNodes' metadata.
  - Only re-import changed functions (detect by comparing AST hashes).

**Acceptance Criteria:**
- Importing the Bumblebee backend itself produces LogicNodes for all functions/methods/classes.
- All CALLS edges between functions are correctly created.
- Variable extraction runs on each imported LogicNode.
- Incremental import of a file with 1 changed function only updates that function's LogicNode.
- Import of 100 files completes in < 30 seconds.

---

### TICKET-831: Import REST Endpoint — DONE

**File:** `backend/app/routers/import_router.py`

**Goal:** Expose the import pipeline via REST API.

**Tasks:**
- `POST /api/v1/import/file` — Import a single file (`{ "path": "..." }`).
- `POST /api/v1/import/directory` — Import a directory (`{ "path": "...", "patterns": ["*.py"] }`).
- `POST /api/v1/import/incremental` — Incremental re-import (`{ "path": "..." }`).
- All endpoints stream progress via WebSocket `import:progress` events.
- Return `ImportReport` with counts: nodes_created, nodes_updated, edges_created, variables_created, errors.

**Acceptance Criteria:**
- Importing a directory returns accurate counts.
- Progress events are emitted for each file processed.
- Errors in individual files don't halt the full import (logged and reported).

---

## Phase 4: VFS Projection Engine — DONE

### TICKET-840: VFS Engine (Graph-to-Files, Bidirectional) — DONE

**File:** `backend/app/services/vfs_engine.py`

**Goal:** Project the graph into human-readable Python files in `.bumblebee/vfs/` (git-tracked) with bidirectional sync.

**Tasks:**
- Implement `project_module(module_path: str) -> str`:
  - Query all LogicNodes with matching `module_path`.
  - Order by original position (or alphabetically for new nodes).
  - Generate import statements from DEPENDS_ON edges.
  - Generate class definitions with MEMBER_OF methods.
  - Generate standalone functions.
  - Reuse `code_generator.py` logic for source reconstruction.
- Implement `project_all(output_dir: str) -> ProjectionReport`:
  - Project all modules to `.bumblebee/vfs/` directory.
  - Mirror the module_path structure as directories.
- Implement `project_node(node_id: str) -> str`:
  - Generate source text for a single LogicNode.
- Implement `sync_vfs_to_graph(vfs_path: str) -> SyncReport` (reverse pipeline):
  - Parse VFS file with tree-sitter.
  - For each function/class: compute AST hash, match against existing LogicNodes.
  - Matching hash → no change. Different hash for same name/signature → update LogicNode. New function → create LogicNode via import pipeline.
  - Deleted function (in graph but not in VFS) → prompt or deprecate.
  - Return report: updated, created, deprecated counts.
- Validate output with tree-sitter: confirm syntactic validity.

**Acceptance Criteria:**
- Projected files are syntactically valid Python (tree-sitter parse succeeds).
- Round-trip: import a real Python file, project it back, diff shows only formatting differences (not logic changes).
- A module with 3 classes and 10 functions produces correct output with proper ordering.
- VFS files are written to `.bumblebee/vfs/` (git-tracked, committed).
- Reverse sync: editing a function in a VFS file and running sync updates the corresponding LogicNode.
- Reverse sync: adding a new function to a VFS file creates a new LogicNode.

---

### TICKET-841: VFS REST Endpoints + Monaco Integration — DONE

**File:** `backend/app/routers/vfs.py`

**Goal:** Expose VFS projection via API and connect to Monaco editor.

**Tasks:**
- `GET /api/v1/vfs/{module_path}` — Get projected source for a module.
- `GET /api/v1/vfs` — List all available VFS modules.
- `POST /api/v1/vfs/project` — Trigger full VFS projection.
- `GET /api/v1/vfs/node/{node_id}` — Get projected source for a single node.
- Frontend: update Monaco to load files from VFS endpoints instead of raw disk paths.
- Frontend: when user edits in Monaco, send changes back through LogicNode update pipeline.
- `POST /api/v1/vfs/sync` — Trigger reverse sync (VFS → graph) for a module or full VFS.

**Acceptance Criteria:**
- Monaco displays VFS-projected files.
- Editing a function in Monaco triggers a LogicNode update (not a raw file write).
- VFS projection endpoint returns valid Python source.
- Reverse sync endpoint correctly detects new, modified, and deleted functions in VFS files.

---

## Phase 5: Flows & Gap Analysis — DONE

### TICKET-850: Flow Service — DONE

**File:** `backend/app/services/flow_service.py`

**Goal:** CRUD operations for Flows + auto-discovery of common flow patterns.

**Tasks:**
- `create_flow(data: FlowCreate) -> FlowResponse`: Create Flow node + STEP_OF edges.
- `get_flow(flow_id: str) -> FlowResponse`: Fetch with all step nodes and sub-flows.
- `list_flows() -> list[FlowResponse]`: List all flows.
- `update_flow(flow_id: str, data: FlowUpdate) -> FlowResponse`: Update steps, entry/exit points.
- `delete_flow(flow_id: str) -> None`: Remove flow node and STEP_OF edges.
- `add_sub_flow(parent_flow_id: str, child_flow_id: str, step_order: int) -> FlowResponse`:
  - Create CONTAINS_FLOW edge. Update parent's sub_flow_ids.
- `remove_sub_flow(parent_flow_id: str, child_flow_id: str) -> FlowResponse`:
  - Remove CONTAINS_FLOW edge. Update parent's sub_flow_ids.
- `promote_flow_to_node(flow_id: str) -> LogicNodeResponse`:
  - Create a LogicNode with `kind=flow_function` whose source_text calls all constituent LogicNodes in order.
  - Create CALLS edges from the new LogicNode to each step.
  - Set `promoted_node_id` on the Flow. Create PROMOTED_TO edge.
- `get_flow_hierarchy(flow_id: str) -> FlowHierarchy`:
  - Recursively traverse CONTAINS_FLOW edges to return the full tree of flows and sub-flows.
- `discover_flows(entry_node_id: str, max_depth: int) -> list[FlowSuggestion]`:
  - Starting from an entry point, follow CALLS edges to discover linear and branching paths.
  - Return suggested flows for user confirmation.

**Acceptance Criteria:**
- Creating a flow with 5 nodes produces 5 STEP_OF edges with correct ordering.
- Flow discovery from a known entry point suggests meaningful paths.
- Updating a flow's node_ids correctly updates STEP_OF edges.
- Sub-flows: adding a sub-flow creates a CONTAINS_FLOW edge and the hierarchy query returns the correct tree.
- Promote: promoting a flow creates a LogicNode with `kind=flow_function` and CALLS edges to all steps.
- Hierarchy: a 3-level deep flow hierarchy (flow → sub-flow → sub-sub-flow) is correctly traversed.

---

### TICKET-851: Gap Analysis Engine — DONE

**File:** `backend/app/services/gap_analysis.py`

**Goal:** Detect structural gaps, anti-patterns, and opportunities in the graph.

**Tasks:**
- `find_dead_ends(scope: str | None) -> list[LogicNodeResponse]`:
  - LogicNodes with no outgoing CALLS edges and not at the end of a Flow.
- `find_orphans(scope: str | None) -> list[LogicNodeResponse]`:
  - LogicNodes with no incoming edges (never called, never depended on).
- `find_missing_error_handling(scope: str | None) -> list[dict]`:
  - LogicNodes that CALL error-prone nodes (DB, network, file I/O) without being wrapped in try/except.
- `find_circular_deps(scope: str | None) -> list[list[str]]`:
  - Cycles in the CALLS/DEPENDS_ON graph.
- `find_untested_mutations(scope: str | None) -> list[dict]`:
  - Variables that are MUTATED but never READS-validated afterward.
- Return all results as `GapReport`.

**Acceptance Criteria:**
- Dead ends correctly exclude Flow exit points.
- Orphan detection excludes entry points and top-level module functions.
- Circular dependency detection returns the cycle path.
- Gap analysis on a 500-node graph completes in < 2 seconds.

---

### TICKET-852: Flow & Gap REST Endpoints — DONE

**File:** `backend/app/routers/flows.py`, `backend/app/routers/gaps.py`

**Goal:** Expose flow and gap analysis services via REST API.

**Tasks:**
- **Flow endpoints:**
  - `POST /api/v1/flows` — Create a flow
  - `GET /api/v1/flows/{flow_id}` — Get a flow
  - `GET /api/v1/flows` — List all flows
  - `PATCH /api/v1/flows/{flow_id}` — Update a flow
  - `DELETE /api/v1/flows/{flow_id}` — Delete a flow
  - `POST /api/v1/flows/discover` — Auto-discover flows (`{ "entry_node_id": "...", "max_depth": 10 }`)
- **Gap analysis endpoints:**
  - `GET /api/v1/gaps/dead-ends` — Find dead ends (`?scope=`)
  - `GET /api/v1/gaps/orphans` — Find orphans (`?scope=`)
  - `GET /api/v1/gaps/missing-error-handling` — Find missing error handling (`?scope=`)
  - `GET /api/v1/gaps/circular-deps` — Find circular dependencies (`?scope=`)
  - `GET /api/v1/gaps/untested-mutations` — Find untested mutations (`?scope=`)
  - `GET /api/v1/gaps/report` — Full gap report (`?scope=`)

**Acceptance Criteria:**
- All endpoints return proper status codes and Pydantic-validated responses.
- Gap report endpoint aggregates all analysis types into a single response.

---

## Phase 6: Frontend Adaptations — DONE

### TICKET-860: TypeScript Type Updates — DONE

**File:** `frontend/src/types/`

**Goal:** Update all TypeScript types to match the new schema.

**Tasks:**
- Define `LogicNode`, `Variable`, `Flow`, `Edge` interfaces matching backend Pydantic models.
- Define `LogicNodeKind`, `EdgeType`, `ParamSpec`, `MutationTimeline`, `LogicPack`, `GapReport` types.
- Remove old `Module`, `Class`, `Function`, `Statement`, `ControlFlow`, `Branch` types.
- Update API client types for new endpoints.

**Acceptance Criteria:**
- `npm run typecheck` passes with zero errors.
- All API response types match backend OpenAPI schema.

---

### TICKET-861: LogicNode + Flow React Flow Components — DONE

**File:** `frontend/src/graph/nodes/`, `frontend/src/graph/edges/`

**Goal:** Create React Flow custom node and edge components for the new schema.

**Tasks:**
- `LogicNodeNode` — renders function/method/class/constant nodes with kind-based icons and colors.
- `VariableNode` — orange diamond, shows name and type hint.
- `FlowNode` — renders a flow as a grouped container with entry/exit indicators.
- Update edge components for new edge types: DEPENDS_ON, IMPLEMENTS, VALIDATES, TRANSFORMS, MEMBER_OF.
- Keep existing edge components: CALLS, ASSIGNS, MUTATES, READS, PASSES_TO, FEEDS, RETURNS.

**Acceptance Criteria:**
- All LogicNode kinds render with distinct visual treatment.
- Variable nodes display name and type hint.
- Flow containers show step ordering.
- Edge colors and styles match the design system.

---

### TICKET-862: Zustand Store Adaptations — DONE

**File:** `frontend/src/stores/`

**Goal:** Adapt Zustand stores to work with UUID-based LogicNodes instead of file-path-based nodes.

**Tasks:**
- Update `graphStore` to use UUID keys instead of file paths.
- Update navigation: `navigateToNode(nodeId: string)` replaces `drillIntoFile(path)`.
- Update `selectedNode` state to hold `LogicNode | Variable | Flow`.
- Add `flowStore` for managing flow state.
- Update WebSocket handlers for new event types.

**Acceptance Criteria:**
- Clicking a LogicNode navigates by UUID.
- Flow selection loads and displays flow nodes.
- WebSocket `graph:updated` events trigger correct store updates.

---

### TICKET-863: Semantic Diff Visualization — DONE

**File:** `frontend/src/components/SemanticDiff.tsx`

**Goal:** Visualize semantic diffs from the diff engine on the graph canvas.

**Tasks:**
- Render added LogicNodes with green dashed borders.
- Render deprecated LogicNodes with red strikethrough.
- Render modified LogicNodes with yellow highlight + inline source diff.
- Render added/removed edges with green/red dashed lines.
- Show a diff summary panel: counts of added/modified/deprecated nodes and edges.
- Integration with Git: show diff between current graph and last committed `.bumblebee/` state.

**Acceptance Criteria:**
- A diff with 3 added, 2 modified, 1 deprecated node renders correctly on the canvas.
- Clicking a modified node shows old vs new source text.
- Diff summary panel shows accurate counts.

---

## Phase 7: Agent Toolchain — DONE (scaffolded)

### TICKET-870: Agent Tool Executor — DONE

**File:** `backend/app/services/agent_tools.py`

**Goal:** Implement the full agent toolchain for the new schema.

**Tasks:**
- **Query tools (read-only):**
  - `find_node(query, kind?, limit?)` — delegates to `logic_node_service.find_nodes`
  - `get_node(hash_id)` — delegates to `logic_node_service.get_node`
  - `get_dependencies(hash_id, depth?, edge_types?)` — delegates to `edge_service.get_dependencies`
  - `get_dependents(hash_id, depth?)` — delegates to `edge_service.get_dependents`
  - `get_variable_timeline(variable_id)` — delegates to `variable_timeline_service`
  - `trace_variable(name, scope?)` — delegates to `variable_timeline_service.trace_variable`
  - `get_logic_pack(hash_id, hops?)` — builds Logic Pack subgraph
  - `get_flow(flow_id)` — delegates to `flow_service.get_flow`
  - `find_gaps(scope, analysis_type)` — delegates to `gap_analysis`
  - `run_cypher(query, params)` — raw graph query
  - `project_vfs(scope, format)` — delegates to `vfs_engine`
- **Mutation tools (write operations):**
  - `create_node(name, kind, source_text, semantic_intent?, tags?)` — delegates to `logic_node_service.create_node`
  - `update_node(hash_id, new_source_text)` — delegates to `logic_node_service.update_node`
  - `deprecate_node(hash_id, replacement?)` — delegates to `logic_node_service.deprecate_node`
  - `add_edge(source, target, type, properties?)` — delegates to `edge_service.add_edge`
  - `remove_edge(source, target, type)` — delegates to `edge_service.remove_edge`
  - `create_flow(name, node_hash_ids, entry_point, exit_points?)` — delegates to `flow_service.create_flow`
- Register all tools in OpenAI-compatible tool-use format for Ollama.

**Acceptance Criteria:**
- All 17 tools are registered and callable via the chat endpoint.
- Each tool delegates to the correct service and returns structured results.
- Tool schemas are valid OpenAI tool-use format.
- Error handling: invalid node IDs return clear error messages, not stack traces.

---

### TICKET-871: LLM-Powered Semantic Intent Generation — DONE

**File:** `backend/app/services/semantic_intent.py`

**Goal:** Auto-generate `semantic_intent` descriptions for LogicNodes using the LLM.

**Tasks:**
- Implement `generate_intent(node: LogicNode) -> str`:
  - Build a prompt with the node's source_text, signature, and immediate edges.
  - Call the LLM (via ModelAdapter) to generate a one-line description.
  - Cache results to avoid redundant LLM calls.
- Implement `batch_generate_intents(node_ids: list[str]) -> dict[str, str]`:
  - Generate intents for multiple nodes efficiently.
- Hook into the import pipeline: after importing, optionally generate intents for all new nodes.
- Hook into `create_node`: if `semantic_intent` is not provided, auto-generate it.

**Acceptance Criteria:**
- Generated intents are concise (< 100 chars) and accurately describe the node's purpose.
- Batch generation processes 100 nodes in < 60 seconds with a local 7B model.
- Cached intents are not re-generated unless the node's source_text changes.

---

## Phase 8: Documentation — IN PROGRESS

### TICKET-880: Rewrite `docs/vision.manifesto.md` — DONE

**Goal:** Replace the existing manifesto with the Code-as-Data vision.

**Content:** Two-tier node model (LogicNodes + Variables), VFS projections, Graph-to-Git serialization, agent-native interface, mutation timeline as killer feature.

**Acceptance Criteria:** Manifesto clearly communicates the inversion: graph is source of truth, files are projections.

---

### TICKET-881: Update `docs/arch.core.md + docs/arch.compose.md + docs/tech.stack.md` — BACKLOG

**Goal:** Add new architecture decisions for the Code-as-Data refactor.

**Content:** Serialization format (JSON in Git), hash identity (UUID7 + SHA-256), VFS strategy, variable nodes rationale, edge manifest design, node identity rules.

**Acceptance Criteria:** All new technical decisions are documented with rationale.

---

### TICKET-882: Replace `docs/project.tickets.md` — DONE

**Goal:** Replace the existing ticket backlog with the 800-series phased plan.

**Content:** Full acceptance criteria for all tickets across 8 phases.

**Acceptance Criteria:** Tickets reference `spec.schema.md` for format specs. Execution order is clear.

---

### TICKET-883: Create `spec.schema.md` — DONE

**Goal:** Full JSON schema specification for the `.bumblebee/` serialization format.

**Content:** LogicNode, Variable, Edge manifest, Flow, meta.json — with example JSON for each. FalkorDB index definitions. Key Cypher query patterns.

**Acceptance Criteria:** A developer can implement the serializer/deserializer from this spec alone.

---

## Execution Order

```
Phase 8 (docs) ─── can start immediately, no code dependencies

Phase 0 (foundation) ─┬─ Phase 1 (CRUD) ─┬─ Phase 3 (import) ─── test with real repo data
                       │                   ├─ Phase 4 (VFS)
                       │                   ├─ Phase 5 (flows + gaps)
                       │                   └─ Phase 6 (frontend)
                       └─ Phase 2 (serialization) ──── Phase 7 (agent toolchain)
```

**Recommended single-developer order:**

Phase 8 (docs) → Phase 0 → Phase 1 → Phase 3 → Phase 2 → Phase 4 → Phase 5 → Phase 6 → Phase 7

---

# Backlog

## TICKET-701: Variable Data-Flow Tracing

**Priority:** Backlog
**Area:** Frontend + Backend

Double-click a variable node to highlight its full data-flow path through the graph:

- **Upstream:** where the variable's value originates (parameters, assignments, returns from other functions)
- **Downstream:** where the variable flows to — function calls it's passed into, mutations applied to it, other variables it contributes to
- Traces in both directions until exit of a flow

**Starting points:**
- Backend: transitive graph traversals over READS, MUTATES, PASSES_TO, RETURNS edges
- Frontend: `traceVariable` store action and `traceRef` rendering path in `AtlasOverview.tsx`

---

## TICKET-702: Graph-Aware Function Editor Pane — SUPERSEDED BY 900-SERIES

**Status:** Superseded by TICKET-900 through TICKET-922 (Compose Tab).
See Phase 9-11 in the 900-series for the full implementation plan.

---

## TICKET-703: Cypher Query Graph Filter — PARTIALLY COVERED BY 900-SERIES

**Priority:** Backlog (selection mechanism feeds into TICKET-940)
**Area:** Frontend + Backend

Run Cypher queries against FalkorDB and filter/highlight the Atlas graph view to show only matching results:

1. Query input UI component
2. Backend endpoint that proxies Cypher to FalkorDB and returns matching node/edge IDs
3. Frontend filters the Sigma view to show/highlight matches (dim non-matches)
4. Enables ad-hoc exploration: "show all functions that call X", "show all classes inheriting from Y"
5. **900-series integration:** Query results become the selection mechanism for virtual script assembly (TICKET-940). Highlighted nodes → "Assemble" button → virtual script tab.

**Starting points:**
- Frontend: `nodeReducer`/`edgeReducer` pattern in `AtlasOverview.tsx` (same as trace dimming)
- Backend: FalkorDB client already available via FastAPI lifespan


## TICKET-704: Bring your dependencies, bring your api, bring your mcp

**Priority:** Backlog
**Area:** Backend

Dependency and packages are part of the functional blocks avaliable to use and should be treated as such. Available in 
queries and when building 

THIS TICKET IS IN DEVELOPMENT AND NEEDS FLESHING OUT


---

# 900-Series: VFS Compose & Virtual Script

> **Core principle:** The graph becomes a live, editable surface. Users author new logic (Compose Tab) and assemble existing logic (Virtual Script View) through the same editor. Deterministic graph queries drive suggestions; LLM judges compatibility.

See `docs/subsystem.vfs-compose.md` for the full design document.

---

## Phase 9: Editor Tab System (Foundation)

### TICKET-900: Refactor editorStore to Multi-Tab Architecture

**File:** `frontend/src/store/editorStore.ts`

**Goal:** Replace single-view editor state with a multi-tab system. All tabs are writable.

**Tasks:**
- Define `EditorTab` type with fields for all origins:
  - `id: string` (UUID)
  - `label: string`
  - `nodeId: string | null` — set when opened from a graph node (editing existing LogicNode)
  - `modulePath: string` — module path for the tab's content
  - `content: string` — editor content
  - `language: string`
  - `parseResult: ComposeParseResult | null` — latest parse result
  - `sourceNodeIds: string[]` — node IDs (for assembled content or parsed content)
  - `flowId: string | null` — if saved as a Flow
  - `gaps: Gap[] | null` — missing variables from assembly
  - `isDirty: boolean` — unsaved changes to an existing node
- Replace `activeNodeView` + `nodeViewHistory` with `tabs: EditorTab[]` + `activeTabId: string | null`.
- Implement actions: `openTab`, `closeTab`, `setActiveTab`, `updateTabContent`, `setComposeResult`, `setAssemblyResult`, `markDirty`, `markClean`.
- `openNodeView(view)` opens an existing node's source in an editable tab (creates/reuses tab with matching `nodeId`).
- A tab can start empty ("+"), from a graph node click, or pre-populated via assembly. All are the same editable surface.

**Acceptance Criteria:**
- Clicking a graph node opens an editable tab with the node's source.
- Editing and saving an existing node updates the LogicNode in the graph.
- "+" creates a new empty tab for authoring from scratch.
- Multiple tabs can be open simultaneously.
- Tab state persists across tab switches.
- `npm run typecheck` passes.

---

### TICKET-901: Update TabBar for Multi-Tab Rendering

**File:** `frontend/src/components/layout/TabBar.tsx`

**Goal:** Replace history breadcrumb with a real multi-tab bar.

**Tasks:**
- Render each tab from `editorStore.tabs` as a clickable pill.
- Active tab gets highlight styling.
- Close button on each tab.
- Dirty indicator (dot) on tabs with unsaved changes to existing nodes.
- "+" button to create a new empty compose tab.
- Tabs show: node name (if opened from graph), "Untitled" (if new), or assembled flow name.
- Support tab overflow (horizontal scroll or dropdown).

**Acceptance Criteria:**
- Tabs are clickable and closable.
- Dirty indicator shows when an existing node has been modified.
- "+" button creates a new tab and switches to it.
- TabBar renders correctly with 1-10+ tabs.

---

### TICKET-902: CodeEditor Supports Writable Tabs

**Files:** `frontend/src/components/editor/CodeEditor.tsx`, `frontend/src/editor/ModelManager.ts`

**Goal:** Make Monaco always writable and support multiple tab models.

**Tasks:**
- CodeEditor reads `activeTab` from `editorStore` instead of `activeNodeView`.
- All tabs are writable. Remove `readOnly: true` from Monaco options.
- URI scheme: `bumblebee://node/{nodeId}` for existing nodes, `bumblebee://compose/{tabId}` for new/assembled content.
- Register `onDidChangeModelContent` → `updateTabContent` + `markDirty` on all tabs.
- ModelManager: add `getOrCreateTabModel(tabId, content, language)`, `disposeTabModel(tabId)`.

**Acceptance Criteria:**
- Typing in a compose tab updates content live.
- Switching between tabs preserves content and cursor position.
- Node-view tabs remain read-only.
- Monaco models are properly disposed when tabs are closed.

---

### TICKET-903: Layout Verification for Tab System

**File:** `frontend/src/components/layout/Layout.tsx`

**Goal:** Verify layout panels work correctly with the new tab system.

**Tasks:**
- Verify panel collapse/expand works with all tab kinds.
- ExternalRefsPanel only renders for `node-view` tabs.
- ComposeSuggestionsPanel renders for `compose` tabs (TICKET-921).

**Acceptance Criteria:**
- No visual regressions. All panel interactions work.

---

## Phase 10: Compose Tab — Backend

### TICKET-910: Cypher Queries for Variable/Type Matching — DONE

**File:** `backend/app/graph/logic_queries.py`

**Goal:** Add Cypher templates for finding LogicNodes by parameter type, return type, and parameter name.

**Tasks:**
- `FIND_NODES_BY_PARAM_TYPE`: Match active LogicNodes whose `params` JSON contains a given type hint.
- `FIND_NODES_BY_RETURN_TYPE`: Match active LogicNodes with a given `return_type`.
- `FIND_NODES_BY_PARAM_NAME`: Match active LogicNodes whose `params` JSON contains a given param name.

**Acceptance Criteria:**
- `FIND_NODES_BY_PARAM_TYPE` with `"str"` returns functions that accept `str` parameters.
- `FIND_NODES_BY_RETURN_TYPE` with `"bool"` returns functions returning `bool`.
- Queries are parameterized (no string interpolation). Results are limited.

---

### TICKET-911: Suggestion Service (Deterministic)

**File:** `backend/app/services/compose/suggestion_service.py`

**Goal:** Given a set of variables (from a parse), find LogicNodes whose params or return types match.

**Tasks:**
- `get_suggestions(variables: list[VariableNode]) -> list[Suggestion]`:
  - For each variable with `type_hint`: query `FIND_NODES_BY_PARAM_TYPE` + `FIND_NODES_BY_RETURN_TYPE`.
  - For each variable without `type_hint`: query `FIND_NODES_BY_PARAM_NAME`.
  - Parse the JSON `params` field in Python for precise matching (Cypher `CONTAINS` is a fast pre-filter).
  - Deduplicate, rank: exact type match > partial type match > name match.
- Return: `[{ variable_name, type_hint, matching_nodes: [{ id, name, signature, match_reason }] }]`.

**Acceptance Criteria:**
- Given a `config: Config` variable, finds functions that accept `Config` as a parameter.
- Given a `result: str` variable, finds functions that return `str`.
- No LLM calls. Purely deterministic.

---

### TICKET-912: POST /api/v1/compose/parse Endpoint — DONE

**File:** `backend/app/routers/compose.py`

**Goal:** Receive editor content, parse it, upsert into the graph, and return suggestions.

**Tasks:**
- Accept `{ source: string, module_path: string }`.
- Call `parse_file(source, module_path)` — same tree-sitter parser as batch import.
- Call `import_file(module_path, source)` — same import pipeline. Produces identical graph result.
- Collect created `node_ids` and `variable_ids`.
- Call suggestion service on extracted variables.
- Broadcast `graph:updated` over WebSocket.
- Return `{ report, node_ids, variable_ids, suggestions }`.
- Compose modules use `__compose__.{tab_id}` as `module_path`.
- Register router in `main.py`.

**Acceptance Criteria:**
- Posting a Python function creates a LogicNode in the graph with correct kind, params, return_type.
- Re-posting the same source is idempotent (hash match → no change).
- Suggestions are returned alongside parse results.
- WebSocket `graph:updated` event fires after successful parse.

---

### TICKET-913: Save & Impact Analysis (Edit Existing Node) — DONE

**Files:** `backend/app/routers/compose.py`, `frontend/src/store/graphStore.ts`, `frontend/src/components/canvas/AtlasOverview.tsx`

**Goal:** When a user edits an existing LogicNode and saves, update the graph and highlight affected downstream functions.

**Tasks:**
- Backend: `POST /api/v1/compose/save` endpoint.
  - Accept `{ node_id: string, source: string }`.
  - Update the LogicNode in FalkorDB via `logic_node_service.update_node()` (recompute hash, re-extract variables).
  - **No filesystem writes.** This updates the graph only. VFS projection is a separate on-demand operation.
  - Run `IMPACT_ANALYSIS` query on the updated node.
  - Detect signature changes (params/return_type) → find all CALLS edges pointing at this node → those callers are potentially broken.
  - Return `{ updated_node, impacted_nodes: [{ id, name, reason }] }`.
  - Broadcast `graph:updated` + `node:pulse` over WebSocket.
- Frontend: on save (Cmd+S), call save endpoint.
  - On success: mark tab clean, update `impactedNodeIds` in graphStore.
  - In `nodeReducer`: impacted nodes get red highlight with pulsing animation.
  - Impact highlights auto-clear after 10 seconds or on next user action.

**Acceptance Criteria:**
- Editing a function's signature and saving highlights all callers in red on the graph.
- Editing only the body (no signature change) shows impact on downstream READS consumers.
- Impact highlights are visually distinct (red, pulsing) and temporary.
- Tab dirty indicator clears on save.

---

## Phase 11: Compose Tab — Frontend

### TICKET-920: Compose Sync Hook

**Files:** `frontend/src/hooks/useComposeSync.ts`, `frontend/src/api/compose.ts`

**Goal:** Debounced live sync from compose tab to backend parse endpoint.

**Tasks:**
- `useComposeParse()` TanStack Query mutation wrapping `POST /api/v1/compose/parse`.
- `useComposeSync(tabId)` custom hook:
  - Watch `content` changes on the active compose tab.
  - Debounce 500ms via `setTimeout`.
  - Call parse mutation.
  - On success: store `node_ids` + `suggestions` in tab state via `setComposeResult`.
  - Update `graphStore.setComposeContext(node_ids)` for the compose lens.

**Acceptance Criteria:**
- Typing in compose tab triggers a parse 500ms after last keystroke.
- Parse results populate the suggestion panel.
- Graph view updates to show compose lens.

---

### TICKET-921: Compose Suggestions Panel

**File:** `frontend/src/components/panels/ComposeSuggestionsPanel.tsx`

**Goal:** Display variable-aware function suggestions when a compose tab is active.

**Tasks:**
- Render when active tab is `compose` (replaces ExternalRefsPanel position).
- List suggestions grouped by variable name.
- Each suggestion shows: function name, signature, match reason.
- Click a suggestion: insert a call to that function at cursor position in Monaco.
- Show parse status: syncing indicator, error count.

**Acceptance Criteria:**
- Suggestions update after each parse cycle.
- Clicking a suggestion inserts valid function call syntax.
- Empty state shown when no suggestions available.

---

### TICKET-922: Compose Lens in Graph View

**Files:** `frontend/src/store/graphStore.ts`, `frontend/src/components/canvas/AtlasOverview.tsx`

**Goal:** When a compose tab is active, fade non-relevant nodes in the Atlas graph view.

**Tasks:**
- Add `composeContextNodeIds: Set<string>` to graphStore.
- Add actions: `setComposeContext(nodeIds)`, `clearComposeContext()`.
- In `nodeReducer`: if `composeContextNodeIds.size > 0`:
  - Compose context nodes → bright, highlighted, z-index 2.
  - 1-hop neighbors → slightly dimmed, z-index 1.
  - Everything else → faded to near-invisible (rgba(60,60,60,0.12)).
- Use a ref for Sigma callback performance (same pattern as `highlightRef`).
- Clear compose context when compose tab is closed.

**Acceptance Criteria:**
- Graph view clearly shows which nodes are in the compose context.
- Non-relevant nodes are visually faded but still clickable.
- Closing compose tab restores full graph visibility.

---

## Phase 12: Virtual Script View — Backend

### TICKET-930: Cypher Queries for Script Assembly

**File:** `backend/app/graph/logic_queries.py`

**Goal:** Add queries to support script assembly from multiple LogicNodes.

**Tasks:**
- `GET_CLASS_FOR_METHOD`: Follow `MEMBER_OF` edge from method to class, include `__init__` params.
- `GET_NODE_DATA_FLOW`: Get all ASSIGNS/READS/RETURNS variables for a LogicNode.

**Acceptance Criteria:**
- `GET_CLASS_FOR_METHOD` returns class name + constructor params for any method.
- `GET_NODE_DATA_FLOW` returns complete variable lists grouped by role (assigns/reads/returns).

---

### TICKET-931: Script Assembler Service

**File:** `backend/app/services/compose/script_assembler.py`

**Goal:** Given a set of LogicNode IDs, generate a script that wires their inputs and outputs together.

**Tasks:**
- `assemble_script(node_ids: list[str], query_mode: str) -> AssemblyResult`:
  1. Fetch each LogicNode by ID.
  2. For methods with `self` param: follow `MEMBER_OF` → get class + `__init__` params.
  3. Query each node's data flow (ASSIGNS/READS/RETURNS).
  4. Build data-flow dependency graph: output of node A feeds input of node B.
  5. Topological sort the selected nodes.
  6. Generate script: imports (from DEPENDS_ON edges) → class instantiations → function calls wired by variable names.
  7. Identify gaps: variables needed (READS) but not produced (ASSIGNS/RETURNS) by any selected node.
  8. Return `{ script, imports, gaps: [{ variable_name, type_hint, needed_by }], class_context }`.
- `query_mode` filter: `"explore"` = full graph, `"vfs"` = only `__compose__` module_path nodes.

**Acceptance Criteria:**
- Three functions with compatible types produce a wired script with correct variable assignments.
- Methods with `self` include class instantiation with constructor params.
- Missing variables appear as `# GAP: variable_name (type)` comments.
- Topological sort handles diamond dependencies.
- Import statements are generated from DEPENDS_ON edges.

---

### TICKET-932: POST /api/v1/compose/assemble Endpoint

**File:** `backend/app/routers/compose.py` (extend)

**Goal:** Expose the script assembler as an API endpoint.

**Tasks:**
- Accept `{ node_ids: string[], query_mode: "explore" | "vfs" }`.
- Call `assemble_script()`.
- Return `{ script, imports, gaps, class_context }`.

**Acceptance Criteria:**
- Valid response for 1-20 selected nodes.
- Gaps are returned as structured data (not just comments in the script).
- Error handling for invalid node IDs.

---

## Phase 13: Assembly into Compose — Frontend

### TICKET-940: Assemble into Compose Tab

**Files:** `frontend/src/store/editorStore.ts`, `frontend/src/api/compose.ts`

**Goal:** Populate a compose tab with assembled content from a graph node selection.

**Tasks:**
- Add `openComposeFromAssembly(nodeIds, content, gaps)` action to editorStore — creates a compose tab pre-populated with assembled script.
- Add `useAssembleScript()` TanStack Query mutation wrapping `POST /api/v1/compose/assemble`.
- Entry points:
  - "Assemble" button in graph view toolbar (when nodes are highlighted via Cypher query).
  - Agent command (via terminal chat).
- On click: call assemble endpoint, open compose tab with result. The tab has `sourceNodeIds` populated for context.

**Acceptance Criteria:**
- Highlighting nodes via Cypher query and clicking "Assemble" opens a compose tab with assembled content.
- Tab contains the assembled script with gap comments.
- Tab behaves identically to a manually-created compose tab (live sync, suggestions, editable).

---

### TICKET-941: Gap Highlighting in Monaco

**File:** `frontend/src/components/editor/CodeEditor.tsx`

**Goal:** Visually highlight gaps (missing variables) in compose tabs that have assembled content.

**Tasks:**
- For compose tabs with `gaps` data: parse content for `# GAP:` comments.
- Apply Monaco decorations: warning color background on gap lines.
- Glyph margin indicators for gap lines.
- Gaps also listed in suggestion panel (reuse ComposeSuggestionsPanel) with resolution options.

**Acceptance Criteria:**
- Gap lines are visually distinct (yellow/amber background).
- Glyph margin shows warning icon on gap lines.
- Clicking a gap in the suggestion panel scrolls to it in the editor.

---

### TICKET-942: Save Compose Tab as Flow

**Files:** `frontend/src/components/editor/CodeEditor.tsx` (or new toolbar component)

**Goal:** Allow users to save a compose tab's content as a Flow in the graph.

**Tasks:**
- Add "Save as Flow" button in compose tab toolbar (visible when tab has `sourceNodeIds` or parsed `node_ids`).
- On click: call `POST /api/v1/flows` with `node_ids` from the tab, entry/exit points derived from script order.
- Uses existing `FlowCreate` model and `create_flow()` from `flow_service.py`.
- Store returned `flow_id` on the tab.
- Subsequent saves: call `PATCH /api/v1/flows/{flow_id}` (update).

**Acceptance Criteria:**
- "Save as Flow" creates a Flow node with correct STEP_OF edges.
- Re-saving updates the existing Flow rather than creating a duplicate.
- Flow appears in the graph and is queryable.

---

### TICKET-943: Query Mode Toggle

**File:** New small component in editor toolbar area.

**Goal:** Toggle between "explore" (full graph) and "compose" (VFS only) scope for assembly and suggestions.

**Tasks:**
- Render toggle when active tab is `compose`.
- Toggle value controls `query_mode` parameter on assemble endpoint and suggestion scope.
- Re-assemble on toggle change.

**Acceptance Criteria:**
- Toggle switches between explore/compose scope.
- Script regenerates with the new scope.

---

## Phase 14: LLM Compatibility Layer (Future)

### TICKET-950: LLM Suggestion Evaluator

**File:** `backend/app/services/compose/llm_evaluator.py`

**Goal:** LLM reviews deterministic suggestions and provides compatibility judgments.

**Tasks:**
- After suggestion service returns matches, build a Logic Pack context for the compose session.
- Send to LLM with prompt: "Given these variables and these candidate functions, evaluate compatibility. For partial matches, explain what's missing and how to bridge the gap."
- LLM uses agent tools (`find_node`, `get_variable_timeline`, `run_cypher`) to query the graph for additional context.
- Return enriched suggestions: `{ ...suggestion, llm_verdict: string, llm_fix_hint: string }`.

**Acceptance Criteria:**
- LLM correctly identifies partial matches (e.g., "3 of 4 params available").
- LLM suggests graph functions that could produce missing variables.
- LLM does NOT fabricate variables or data — only references graph entities.
- Degrades gracefully if LLM is unavailable (deterministic suggestions still work).

**Note:** This ticket is future work. The deterministic suggestion layer (TICKET-911) ships first and is useful standalone.

---

### TICKET-951: LLM Script Assembly Review

**File:** `backend/app/services/compose/llm_evaluator.py` (extend)

**Goal:** LLM reviews assembled scripts and produces a compatibility report.

**Tasks:**
- After script assembler generates a script, send it + the Logic Packs for all involved nodes to the LLM.
- LLM produces: type compatibility report, suggested reorderings, recommended additional functions from the graph.
- LLM can suggest edits to the script (via the existing edit/preview pipeline).

**Acceptance Criteria:**
- LLM review catches type mismatches that the deterministic assembler misses.
- Suggestions reference real graph nodes (not hallucinated functions).
- Review is optional — script is usable without it.

---

### TICKET-952: Batch Variable Type Inference

**File:** `backend/app/services/compose/type_inference.py`

**Goal:** Use batch LLM inference to strongly type and normalize variable names across a codebase.

**Tasks:**
- For variables without `type_hint`, use LLM to infer types from context (usage patterns, function signatures, docstrings).
- Normalize variable naming: identify semantically equivalent variables with different names.
- Store inferred types as `type_hint` on Variable nodes (flagged as `inferred`, not `declared`).
- Improves suggestion accuracy for untyped codebases.

**Acceptance Criteria:**
- Inferred types are stored with a flag distinguishing them from declared types.
- Variable name normalization identifies semantic equivalences.
- Batch processing handles 1000+ variables efficiently.

**Note:** Backlog item. Improves suggestion quality but not required for v1.

---

## Phase 15: TypeShape — Structural Type Inference (960-Series)

### TICKET-960: TypeShape Graph Schema + Cypher Queries — DONE

**File:** `backend/app/graph/logic_queries.py`

**Goal:** Define TypeShape node indexes and all MERGE/GET/BATCH Cypher templates, plus HAS_SHAPE, ACCEPTS, PRODUCES, COMPATIBLE_WITH edge queries.

---

### TICKET-961: ShapeEvidence Extraction from Variable Usage — DONE

**File:** `backend/app/services/parsing/variable_extractor.py`

**Goal:** Collect structural evidence (attribute access, subscript access, method calls) from AST during variable extraction. Produces `ShapeEvidence` dataclass per variable.

---

### TICKET-962: TypeShape Builder Service — DONE

**File:** `backend/app/services/analysis/type_shape_service.py` (new)

**Goal:** Build TypeShape definitions from ShapeEvidence, compute deterministic shape_hash (SHA-256), determine kind (primitive/generic/structural/hint), and compute COMPATIBLE_WITH edges between shapes.

---

### TICKET-963: TypeShape Integration in Import Pipeline — DONE

**File:** `backend/app/services/persistence/import_pipeline.py`

**Goal:** Create TypeShape nodes and HAS_SHAPE/ACCEPTS/PRODUCES edges during file import. Run COMPATIBLE_WITH computation after batch import.

---

### TICKET-964: TypeShape Serialization — DONE

**File:** `backend/app/services/persistence/serializer.py`

**Goal:** Serialize TypeShape nodes to `.bumblebee/type_shapes/<shape_hash>.json`.

---

### TICKET-965: TypeShape Deserialization — DONE

**File:** `backend/app/services/persistence/deserializer.py`

**Goal:** Deserialize TypeShape nodes from `.bumblebee/type_shapes/` back into FalkorDB on load.

---

### TICKET-966: TypeShape REST API — DONE

**File:** `backend/app/routers/type_shapes.py` (new)

**Goal:** Expose TypeShape queries via REST: consumers by variable, producers by node, search by attributes, detail by shape ID.

**Endpoints:**
- `GET /api/v1/type-shapes/{variable_id}/consumers`
- `GET /api/v1/type-shapes/{node_id}/producers`
- `GET /api/v1/type-shapes/search?attrs=name,email`
- `GET /api/v1/type-shapes/detail/{shape_id}`

---

### TICKET-967: TypeShape Pydantic Models + Tests — DONE

**Files:** `backend/app/models/logic_models.py`, `backend/tests/test_type_shapes.py` (new)

**Goal:** Add TypeShapeResponse model, extend EdgeType enum with HAS_SHAPE/ACCEPTS/PRODUCES/COMPATIBLE_WITH. 30 tests covering shape building, hashing, compatibility, serialization round-trip, and API endpoints.

---

## Execution Order

```
Phase 9 (Tab System)  ──────────────────────────────────────────┐
  900 editorStore → 901 TabBar → 902 CodeEditor → 903 Layout    │
                                                                  │
Phase 10 (Backend Compose)                                        │
  910 Cypher queries → 911 Suggestion service → 912 Endpoint     │
                                                                  │
Phase 11 (Frontend Compose) ← depends on Phase 9 + Phase 10      │
  920 Sync hook, 921 Suggestion panel, 922 Compose lens          │
                                                                  │
Phase 12 (Backend Virtual Script) ← depends on Phase 10          │
  930 Cypher queries → 931 Assembler → 932 Endpoint              │
                                                                  │
Phase 13 (Frontend Virtual Script) ← depends on Phase 9 + 12    │
  940 Tab creation, 941 Gap highlights, 942 Save Flow, 943 Toggle│
                                                                  │
Phase 14 (LLM Layer) ← depends on Phase 11 + Phase 13           │
  950 Suggestion evaluator, 951 Assembly review, 952 Type inference│
                                                                  │
Phase 15 (TypeShape) ← depends on Phase 10 (Variable extraction) │
  960 Schema, 961 Evidence, 962 Builder, 963 Import, 964-965 Serde│
  966 API, 967 Models+Tests                                       │
```

**Recommended build order:**

Phase 9 → Phase 10 → Phase 11 → Phase 12 → Phase 13 → Phase 14

Phase 9 and Phase 10 can be built in parallel (frontend and backend are independent).

---

## Verification Plan

1. **Import pipeline test:** Import the bumblebee_ide backend itself, verify all functions become LogicNodes with correct hash IDs and edges.
2. **Round-trip test:** Serialize graph to `.bumblebee/`, clear FalkorDB, deserialize, verify graph is identical.
3. **VFS test:** Project graph to virtual files, parse with tree-sitter, verify syntax validity.
4. **Semantic diff test:** Make a node change, compute diff, verify correct added/deprecated/remapped report.
5. **Agent tool test:** Use each agent tool via the chat endpoint, verify correct graph operations.
