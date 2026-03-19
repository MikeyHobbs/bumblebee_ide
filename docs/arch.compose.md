# Compose & TypeShape Architecture Decisions

VFS Compose, virtual script assembly, and structural type inference architecture.

---

## 12. VFS Compose & Virtual Script Architecture (900-Series)

See `subsystem.vfs-compose.md` for the full design document.

### 12.1 Multi-Tab Editor — All Tabs Are Writable

**Decision: The editor becomes a multi-tab system. Every tab is writable. There is no read-only mode.**

| Tab Origin | Behavior |
|------------|----------|
| Clicked a graph node | Opens existing LogicNode source, editable. Save → update LogicNode → impact analysis → highlight breaking functions in red. |
| Created new ("+") | Empty editor. Live sync creates new LogicNodes as you type. |
| Assembled from query | Pre-populated with assembled script. Same live sync + suggestions. |

- **Why no read-only:** The user wants to click a node, edit it, save, and immediately see graph impact. A read-only → edit mode toggle adds friction without value. The graph is the source of truth, so editing code *is* editing the graph — make that direct.
- **Impact on save:** When editing an existing LogicNode, saving triggers the `IMPACT_ANALYSIS` Cypher query. Functions that would break (downstream READS of mutated variables, signature changes affecting callers) are highlighted in red on the graph canvas. This makes consequences visible immediately.
- **Backward compatibility:** `openNodeView()` opens an existing node's tab (now editable). All existing graph-click-to-editor navigation is unchanged — it just lands on a writable surface.

### 12.2 Live Compose Sync Pipeline

**Decision: Compose tabs sync to the graph via the same `parse_file()` + `import_file()` pipeline as batch import, debounced at 500ms.**

- **Why same pipeline:** A separate "live" codepath would diverge from batch import over time, producing inconsistent graph state. One pipeline, two entry points.
- **Why 500ms debounce:** Fast enough to feel responsive, slow enough to avoid overwhelming the graph with partial parse states. Tree-sitter parsing is < 10ms for typical function-sized snippets.
- **Module path convention:** Compose tabs use `__compose__.{tab_id}` as `module_path` to distinguish compose-authored nodes from imported code.

### 12.3 Deterministic Suggestions + LLM Judge

**Decision: Function suggestions use deterministic graph queries first. LLM evaluates compatibility as an additive layer.**

The suggestion pipeline is two-tier:

| Tier | Mechanism | When |
|------|-----------|------|
| 1 (v1) | Cypher queries on Variable nodes + LogicNode params/return_type | Always runs |
| 2 (future) | LLM evaluates partial matches, explains gaps, suggests bridges | Additive, optional |

- **Why deterministic first:** Fast, reproducible, no LLM dependency. Works offline. Covers the common case where types match exactly.
- **Why LLM judge:** Real codebases have partial matches (3 of 4 params available), type aliases, implicit conversions, and naming inconsistencies. The LLM adds value by explaining *why* a function is almost usable and *how* to bridge the gap — but it never fabricates variables or data to fill gaps. It operates through graph queries (agent tools), not around them.
- **Future: Batch type inference.** Use LLM to strongly type and normalize variable names across a codebase, improving deterministic suggestion quality.

### 12.4 Virtual Script Assembly

**Decision: Script assembly is deterministic codegen from graph data-flow analysis. LLM reviews the result.**

The assembler:
1. Fetches selected LogicNodes.
2. Queries their Variable edges (ASSIGNS/READS/RETURNS).
3. Builds a data-flow dependency graph between selected nodes.
4. Topological sorts them.
5. Generates imports (from DEPENDS_ON edges), class instantiations (for methods with `self`), and wired function calls.
6. Identifies gaps: variables needed but not produced.

- **Why deterministic first:** The graph already knows inputs/outputs. No need for an LLM to guess what connects to what — the edges tell us.
- **Why gaps, not fabrication:** When a variable is needed but no selected node produces it, the assembler emits a `# GAP:` comment. This is honest — the user or LLM must resolve the gap, not sweep it under fabricated code.
- **Method context:** When a method has `self`, follow `MEMBER_OF` → class + `__init__` params. This is the minimum to make method references usable without pulling entire class hierarchies.

### 12.5 Flows as Ad-Hoc Explorations

**Decision: Virtual scripts are ad-hoc explorations that can optionally be saved as Flows.**

- **Why ad-hoc:** Not every script assembly should become a permanent graph entity. Users explore first, commit when satisfied.
- **Why save as Flow:** The existing Flow model (STEP_OF edges, composable hierarchy, promotable to `flow_function`) is the natural persistence layer. A saved virtual script becomes queryable — if someone's question is answered by an existing Flow, no need to rebuild.
- **Flow reuse:** Query existing Flows before assembling. If a Flow matches the user's intent, surface it directly.

### 12.6 Compose Lens (Graph Filtering)

**Decision: When a compose tab is active, the Atlas graph view fades non-relevant nodes. No second graph view.**

- **Why not a second view:** Maintaining two graph renderers doubles complexity. A lens on the single view is simpler and lets users toggle between focused (compose) and full (explore) modes naturally.
- **Implementation:** Reuse the existing `nodeReducer`/`edgeReducer` pattern from query result highlighting. A `composeContextNodeIds` set drives the lens.

---

## 13. TypeShape: Structural Type Inference (960-Series)

### 13.1 TypeShape as a Hub Node, Not a Property

**Decision: Structural types are first-class graph nodes (TypeShape), not properties on Variable or LogicNode.**

TypeShape nodes act as hubs that multiple variables and functions connect to. This turns type compatibility from O(n*m) pairwise property comparison into O(1) graph traversal via shared shape nodes and COMPATIBLE_WITH edges.

| Approach | Complexity | Query pattern |
|----------|-----------|---------------|
| Type as property on Variable | O(n*m) — compare every variable pair | String matching on JSON blobs |
| TypeShape as hub node | O(1) — follow edges | `MATCH (v)-[:HAS_SHAPE]->(s)<-[:ACCEPTS]-(fn)` |

- **Why hub node:** The compose suggestion pipeline needs to answer "which functions can consume this variable?" instantly. With TypeShape as a hub, this is a single edge traversal. With types as properties, it requires scanning all functions and comparing JSON definitions.
- **Why UUID5 (not UUID7):** TypeShape identity is deterministic from content (shape_hash). UUID5 with a fixed namespace ensures the same shape always gets the same ID, enabling natural deduplication via MERGE.

### 13.2 Evidence-Based Shape Inference

**Decision: Shapes are inferred from usage evidence (attribute access, subscript access, method calls), not solely from type annotations.**

| Evidence source | Example | Inferred shape |
|----------------|---------|----------------|
| Attribute access | `user.name`, `user.email` | `structural: {attrs: [name, email]}` |
| Subscript access | `data["key"]` | `generic: dict` |
| Method call | `items.append(x)` | `generic: list` |
| Type annotation | `x: str` | `hint: str` |

- **Why evidence over annotations:** Real codebases are inconsistently annotated. Evidence from actual usage captures what the code *needs*, not what the developer remembered to declare. A variable accessed as `obj.name` and `obj.email` structurally requires those attributes — this is more useful for compose suggestions than a missing or overly broad annotation.
- **No evidence = no shape:** Variables with no usage evidence and no type annotation get no TypeShape node. This avoids polluting the graph with meaningless `Any` shapes.

### 13.3 COMPATIBLE_WITH as Precomputed Subtyping

**Decision: Shape compatibility (structural subtyping) is precomputed as COMPATIBLE_WITH edges, not evaluated at query time.**

A TypeShape A is COMPATIBLE_WITH TypeShape B if A is a structural superset of B — i.e., A has all the attributes/capabilities that B requires. This is computed once after import and stored as a directed edge.

- **Why precompute:** The compose suggestion query (`"which functions can accept this variable?"`) runs interactively. Computing structural subtyping at query time would add latency proportional to the number of shapes. Precomputed edges make it constant-time.
- **Recomputation trigger:** COMPATIBLE_WITH edges are recomputed when new TypeShape nodes are created (during import or compose save). This is incremental — only new shapes need comparison against existing ones.
