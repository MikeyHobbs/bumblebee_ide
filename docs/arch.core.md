# Core Architecture Decisions: Bumblebee IDE

Foundational architecture decisions that define the code-as-data model, graph rendering, and build sequencing.

---

## 0. Code-as-Data Architecture (800-Series Refactor)

### 0.1 Core Inversion: Graph as Source of Truth

**Decision: The FalkorDB graph is the canonical representation of code. Files are projections.**

Previously, code files were the source of truth and the graph was a mirror for visualization. The 800-series refactor inverts this: LogicNodes in the graph are the atomic units of logic. Files are generated on demand via a VFS projection engine.

- **Why:** AI agents work better with structured, typed graph operations than with raw text file I/O. Graph-native editing eliminates merge conflicts, partial writes, and inconsistent formatting.
- **Impact:** All new code operates on LogicNode CRUD, not file CRUD. The import pipeline converts existing code into graph nodes. The VFS engine projects graph state back to readable files.

### 0.2 Two-Tier Node Model

**Decision: LogicNodes (Tier 1) + Variables (Tier 2). No statement-level graph nodes.**

| Tier | Node Type | Purpose | Who creates |
|------|-----------|---------|-------------|
| 1 | LogicNode | Unit of logic (function, method, class, constant, type_alias) | Agents/humans |
| 2 | Variable | Unit of data flow | Auto-extracted from LogicNode source |

Statements and control flow structures are **internal** to the LogicNode's AST, not separate graph nodes. This is a deliberate simplification from the earlier design (TICKET-104) which had Statement, ControlFlow, and Branch nodes.

- **Why:** Agents query functions and variables, not individual statements. Statement-level nodes create massive graph bloat (10-50x more nodes) without proportional query value. The VFS projection handles rendering control flow for humans.
- **Trade-off:** We lose the ability to do statement-level graph queries (e.g., "find all if-statements"), but gain a dramatically simpler schema that's faster to query and easier for agents to reason about.

### 0.3 Node Identity: Stable UUID + AST Hash

**Decision: UUID7 primary key + SHA-256 AST hash as secondary dedup property.**

| Concern | Approach |
|---------|----------|
| Primary key | UUID7 (time-sortable, globally unique) |
| Deduplication | SHA-256 of canonical AST |
| Edit semantics | Update in-place (same UUID, new hash) |
| Edge stability | Edges reference UUIDs — never need remapping |

- **Why UUID7 over content-hash-as-ID:** Content-addressed identity means every edit changes the node's identity, requiring all edges to be remapped. UUID7 gives stable identity across edits. The AST hash is purely for dedup detection.
- **Edit vs New Node heuristic:** Body logic changes → update in-place. Signature changes (params, return type) → system prompts "Create new or update?" Agent can also explicitly fork via `create_node(derived_from=existing_id)`.

### 0.4 Git Serialization Format

**Decision: JSON files in `.bumblebee/` directory, committed to Git.**

```
.bumblebee/
  meta.json                   # Graph metadata
  nodes/<uuid>.json           # One file per LogicNode
  variables/var_<hash>.json   # Variables grouped by scope
  edges/manifest.json         # All edges in one file
  flows/flow_<name>.json      # Named processes
  vfs/                        # GIT-TRACKED — editable projected files
```

Alternatives considered:

| Option | Rejected because |
|--------|-----------------|
| SQLite dump | Binary — no readable Git diffs |
| Single JSON file | Merge conflicts on every change |
| MessagePack/Protobuf | Not human-readable, requires tooling |
| FalkorDB dump/restore | Opaque, vendor lock-in |

- **Why JSON:** Human-readable diffs, GitHub renders well, universal tooling. One file per node means Git diffs show exactly which nodes changed.
- **Edge manifest:** Single `manifest.json` for now. If it grows beyond ~10MB (unlikely for most projects), shard by edge type: `edges/calls.json`, `edges/depends_on.json`, etc.

### 0.5 VFS Projection Strategy

**Decision: Real `.py` files in `.bumblebee/vfs/`, git-tracked with bidirectional sync.**

The VFS (Virtual File System) engine projects graph state into standard Python files that existing tools can consume — compilers, linters, debuggers, Monaco editor.

- **Why real files (not in-memory):** Some tools require filesystem paths. Real files mean zero integration work.
- **Why git-tracked (not gitignored):** VFS files are the artifact that humans, CI, and external tools consume. Tracking them gives familiar Python diffs in PRs, lets contributors edit without Bumblebee, and ensures the runnable code is always version-controlled.
- **Bidirectional sync:** Graph → VFS on project/serialize. VFS → Graph on file change detection (watcher parses edited VFS files, diffs against LogicNode source, and updates/creates LogicNodes accordingly). New functions added to a VFS file become new LogicNodes via the import pipeline.
- **Conflict resolution:** If both graph and VFS change between syncs, the graph wins for existing nodes (it's the canonical source), but new content in VFS files (new functions, new classes) is imported as new LogicNodes.
- **Monaco integration:** Monaco loads VFS files. Edits flow back through the LogicNode update pipeline, not raw file writes.

### 0.6 Variable Nodes as First-Class Graph Entities

**Decision: Variables are separate graph nodes (Tier 2), not just edge properties.**

- **Why separate nodes:** The mutation timeline query — Bumblebee's killer feature — requires variables to be traced *across* LogicNode boundaries. A variable is created in one function, passed to another, mutated in a third, read in a fourth. This cross-function tracing requires Variable as a node that multiple edges can connect to.
- **Alternative rejected:** Storing variable interactions only as edge properties between LogicNodes. This would require complex edge-to-edge joins to reconstruct timelines and couldn't represent PASSES_TO (variable-to-variable across call boundaries).
- **Auto-extraction:** Variable nodes and their edges (ASSIGNS, MUTATES, READS, RETURNS, PASSES_TO, FEEDS) are automatically extracted whenever a LogicNode is created or updated. Agents don't manage variables directly.

### 0.7 Flows as First-Class, Composable Graph Entities

**Decision: Flows are stored as graph nodes, composable into hierarchies, and promotable to LogicNodes.**

A Flow is a named, curated end-to-end process (e.g., "order processing"). Flows are:
- **Documentation anchors** — they give names to important paths through the codebase.
- **Stable LLM context boundaries** — a Logic Pack for a flow always includes the right nodes.
- **Auto-discoverable** — the system can suggest flows by analyzing CALLS chains from entry points.
- **Composable** — a flow can contain sub-flows via `CONTAINS_FLOW` edges, creating a hierarchy of calls. A "process order" flow might include "validate payment" and "ship inventory" sub-flows.
- **Promotable** — when a flow matures into a stable, reusable process, it can be promoted to a LogicNode (`kind: "flow_function"`) that calls all its constituent LogicNodes. This bridges the gap between curated understanding (flow) and executable code (function).

This is particularly important for scientific computing and data pipelines, where flows represent reproducible processes that must be tracked, shared, reused, and composed into larger workflows.

---

## 5. React Flow vs Cytoscape — The Scaling Question

**Decision: React Flow v12. Do not use Cytoscape.**

Cytoscape.js is a purpose-built graph library with excellent raw performance at 10k+ simultaneously-visible nodes. However, for Bumblebee it is the wrong tool:

- **Cytoscape is not React-native.** Custom node types (the `VariableNode` diamond, gutter icons, mutation badges) are DOM elements you manage manually. In React Flow they are just React components. The DX difference is enormous.
- **Bumblebee uses Semantic Zoom.** At low zoom, only ~50 folder cluster nodes are visible. At mid zoom, ~500 file nodes. At high zoom, ~200 function/variable nodes for the visible area. The total graph may be 100k nodes, but the *simultaneously rendered* count is always small. React Flow v12's built-in virtualization handles this cleanly.
- **The Logic Pack panel is always a small subgraph** (< 50 nodes). React Flow is perfect here.
- **React Flow v12 (not v11).** v12 introduced a full rewrite of the internal rendering pipeline, better TypeScript types, and the `useNodesData` / `useEdgesData` hooks that simplify state sync. The APIs changed significantly — generate all code against v12.

If at scale testing shows React Flow cannot handle the visible node count at maximum zoom on a 100k-node repo, the escape hatch is a **WebGL canvas layer** (e.g., `pixi.js` or `sigma.js`) for the global overview mode only, while keeping React Flow for the Logic Pack panel. Do not reach for Cytoscape.

### 5.1 Layout Libraries

React Flow renders nodes at positions you provide — it does not compute layouts. Two layout libraries cover all Bumblebee use cases:

| Library | Use case | Direction |
|---------|----------|-----------|
| `d3-force` | Global canvas — organic force-directed cluster layout | N/A (physics simulation) |
| `@dagrejs/dagre` | Logic Pack panel — structured DAG layouts | `LR` for mutation timelines, `TB` for call graphs |

**Pattern for d3-force (global canvas):**
```typescript
import { forceSimulation, forceLink, forceManyBody, forceCenter, forceCollide } from "d3-force"

// Run simulation to get {x, y} per node, then:
const nodes = simulation.nodes().map(n => ({
  id: n.id,
  position: { x: n.x, y: n.y },
  data: n.data,
  type: n.label, // "Function" | "Class" | "Variable" etc.
}))
// Pass to <ReactFlow nodes={nodes} />
// Re-run simulation only when graph:updated WebSocket event fires
```

**Pattern for dagre (Logic Pack timeline):**
```typescript
import dagre from "@dagrejs/dagre"

function applyDagreLayout(nodes, edges, direction: "LR" | "TB" = "LR") {
  const g = new dagre.graphlib.Graph()
  g.setGraph({ rankdir: direction, nodesep: 60, ranksep: 100 })
  nodes.forEach(n => g.setNode(n.id, { width: 160, height: 40 }))
  edges.forEach(e => g.setEdge(e.source, e.target))
  dagre.layout(g)
  return nodes.map(n => ({ ...n, position: g.node(n.id) }))
}
```

### 5.2 Custom Edge Types for Mutation Flows

Register one edge component per relationship type. Each is a React component receiving SVG path data:

```typescript
// frontend/src/graph/edges/index.ts
import { MutatesEdge } from "./MutatesEdge"   // red, dashed, animated
import { AssignsEdge } from "./AssignsEdge"   // green, solid
import { PassesToEdge } from "./PassesToEdge" // amber, dashed, arrow label
import { ReadsEdge } from "./ReadsEdge"       // blue, faint
import { CallsEdge } from "./CallsEdge"       // grey, solid

export const edgeTypes = {
  MUTATES: MutatesEdge,
  ASSIGNS: AssignsEdge,
  PASSES_TO: PassesToEdge,
  READS: ReadsEdge,
  CALLS: CallsEdge,
}
```

Example — `MutatesEdge` with animated dash and label:
```typescript
import { BaseEdge, EdgeLabelRenderer, getSmoothStepPath } from "@xyflow/react"

export function MutatesEdge({ sourceX, sourceY, targetX, targetY, data }) {
  const [path, labelX, labelY] = getSmoothStepPath({ sourceX, sourceY, targetX, targetY })
  return (
    <>
      <BaseEdge path={path} style={{ stroke: "#d94444", strokeDasharray: "6 3", strokeWidth: 1.5,
        animation: "dash 1s linear infinite" }} />
      <EdgeLabelRenderer>
        <div style={{ transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)` }}
          className="text-[10px] font-mono text-red-500 bg-[#0a0a0a] px-1">
          {data?.mutation_kind ?? "MUTATES"}
        </div>
      </EdgeLabelRenderer>
    </>
  )
}
```

When building a mutation timeline query result into a React Flow graph, each edge from the API carries its `type` field (`ASSIGNS`, `MUTATES`, etc.) which maps directly to the `edgeTypes` key — no extra translation needed.

---

## 11. Ticket Execution Order

The 800-series refactor follows this dependency chain:

```
Phase 8 (docs) ─── can start immediately, no code dependencies

Phase 0 (foundation: 800-802) ─┬─ Phase 1 (CRUD: 810-813) ─┬─ Phase 3 (import: 830-831)
                                │                             ├─ Phase 4 (VFS: 840-841)
                                │                             ├─ Phase 5 (flows/gaps: 850-852)
                                │                             └─ Phase 6 (frontend: 860-863)
                                └─ Phase 2 (serialization: 820-823) ─── Phase 7 (agent: 870-871)
```

**Recommended single-developer order:**

Phase 8 (docs) → Phase 0 → Phase 1 → Phase 3 → Phase 2 → Phase 4 → Phase 5 → Phase 6 → Phase 7

See `project.tickets.md` for the full 800-series backlog with acceptance criteria.
