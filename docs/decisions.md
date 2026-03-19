# Architecture Decisions: Bumblebee IDE

Answers to all open questions that would otherwise block Claude Code or cause inconsistent code generation.

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

## 1. Dependency & Environment Management

**Decision: `uv` + Python 3.12**

- `uv` for all Python environment and dependency management. Use `uv sync` to install from `pyproject.toml`. No `pip` directly.
- **Python 3.12, not 3.10.** Rationale: 3.10 works but misses meaningful gains. 3.11 brought 10-60% performance improvements and better error messages. 3.12 adds `@override`, improved f-string parsing, and better `asyncio` internals — all relevant to a FastAPI + async graph backend. `uv` manages Python version pinning trivially (`.python-version` file: `3.12`). There is no reason to leave this performance on the table.
- `from __future__ import annotations` is still required in every module for forward-reference compatibility.

```toml
# pyproject.toml (root of backend/)
[project]
name = "bumblebee-backend"
requires-python = ">=3.12"

[tool.uv]
dev-dependencies = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "pytest-asyncio>=0.23",
    "black>=24.0",
    "isort>=5.13",
    "pylint>=3.2",
    "mypy>=1.10",
]
```

---

## 2. Dev Ports (Global Constants)

All services use fixed ports in development. These are the canonical values — hardcode them in `.env.example` and reference them everywhere.

| Service               | Port   | Notes                                    |
|-----------------------|--------|------------------------------------------|
| FastAPI backend       | `8000` | `uvicorn app.main:app --reload`          |
| Vite frontend         | `5173` | Vite default, do not change              |
| FalkorDB              | `6379` | Redis-compatible port                    |
| WebSocket (backend)   | `8000` | Same process as FastAPI via `/ws` path   |

`.env.example`:
```
BACKEND_PORT=8000
FRONTEND_PORT=5173
FALKOR_HOST=localhost
FALKOR_PORT=6379
FALKOR_GRAPH_NAME=bumblebee
WATCH_PATH=/path/to/target/repo
OLLAMA_HOST=http://localhost:11434
ORCHESTRATOR_MODEL=qwen2.5-coder:7b
CYPHER_MODEL=qwen2.5-coder:7b
```

---

## 3. FalkorDB Configuration

```yaml
# docker/docker-compose.yml (falkordb service)
falkordb:
  image: falkordb/falkordb:latest
  ports:
    - "6379:6379"
  environment:
    - FALKORDB_ARGS=--maxmemory 4gb --maxmemory-policy noeviction
  volumes:
    - falkordb_data:/data
```

- **Graph name:** `bumblebee` (single graph for now; prefix with project name if multi-repo support is added later).
- **Authentication:** None in dev. Add `FALKORDB_PASSWORD` env var when deploying externally.
- **Python client:** `falkordb` (the official PyPI package, not the legacy `redisgraph` client).
- **Connection:** Use a singleton `FalkorDB` client instance managed via FastAPI lifespan context (`async with lifespan`). Do not create a new connection per request.

```python
# backend/app/graph/client.py — canonical connection pattern
from falkordb import FalkorDB

_client: FalkorDB | None = None

def get_client() -> FalkorDB:
    global _client
    if _client is None:
        _client = FalkorDB(host=settings.FALKOR_HOST, port=settings.FALKOR_PORT)
    return _client

def get_graph():
    return get_client().select_graph(settings.FALKOR_GRAPH_NAME)
```

---

## 4. Frontend: Full Stack of Decisions

| Concern            | Decision                  | Rationale                                                                        |
|--------------------|---------------------------|----------------------------------------------------------------------------------|
| **Language**       | TypeScript (strict)       | User specified. `"strict": true` in `tsconfig.json`.                            |
| **Framework**      | React 18 + Vite           | Already decided in tickets.                                                      |
| **Styling**        | Tailwind CSS v4           | User specified. Use CSS variables (from `styling.md`) as Tailwind theme tokens.  |
| **State**          | Zustand                   | Lightweight, no boilerplate, works well alongside React Flow's internal state.   |
| **Graph canvas**   | React Flow v12            | See Section 5 for Cytoscape analysis.                                            |
| **Data fetching**  | TanStack Query (React Query v5) | Caching, background refetch, WebSocket integration via `queryClient.invalidate`. |
| **Icons**          | Lucide React              | Minimal, consistent with the monospace aesthetic.                                |

`tsconfig.json` flags: `"strict": true`, `"noUncheckedIndexedAccess": true`, `"exactOptionalPropertyTypes": true`.

No CSS Modules, no styled-components, no Emotion. Tailwind only. Custom design tokens from `styling.md` go in `tailwind.config.ts` as theme extensions.

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

## 6. API Contract (Frontend ↔ Backend)

Base URL: `http://localhost:8000/api/v1`

### REST Endpoints

```
POST   /index                          # Trigger full index of WATCH_PATH
POST   /index/file                     # Trigger partial re-index { "path": "..." }

GET    /graph/nodes                    # All nodes (paginated, filterable by label)
GET    /graph/node/{node_id}           # Single node with edges

GET    /logic-pack/{node_id}           # Logic Pack subgraph for a node
       ?hops=2&type=Function

GET    /variables/{variable_id}/timeline  # Mutation timeline
GET    /variables/search               # ?name=x&scope=module.func

POST   /query                          # Raw Cypher { "cypher": "MATCH ..." }

GET    /impact/{function_id}           # Downstream mutation impact

POST   /chat                           # { "message": "...", "model": "..." }
                                       # Streams SSE: tool calls + response tokens
POST   /chat/tool-result               # Return tool result back to model stream

GET    /models                         # List available Ollama models
POST   /edit/preview                   # Ghost preview { "path", "old_text", "new_text" }
POST   /edit/apply                     # Apply a previewed edit

POST   /codegen/{module_id}            # Generate Python source from graph
POST   /codegen/function/{function_id} # Generate single function source
GET    /graph/function/{function_id}/flow  # Full statement/control flow subgraph
PATCH  /graph/statement/{statement_id} # Update statement source_text
POST   /graph/statement                # Insert new statement
DELETE /graph/statement/{statement_id} # Delete statement
PATCH  /graph/statement/reorder        # Reorder statements { "function_id", "statement_ids": [...] }
```

### WebSocket

```
WS  /ws/graph                          # Server -> client push
    Events:
      graph:updated   { affected_modules: string[] }
      node:pulse      { node_id: string }
      index:progress  { file: string, total: int, done: int }
```

### Shared Types (generate from Pydantic models via `fastapi-cli generate-client` or manual TypeScript mirroring)

```typescript
type NodeLabel = "Module" | "Class" | "Function" | "Variable" |
                 "Statement" | "ControlFlow" | "Branch"
type EdgeType  = "DEFINES" | "CALLS" | "INHERITS" | "IMPORTS" |
                 "ASSIGNS" | "MUTATES" | "READS" | "PASSES_TO" | "RETURNS" |
                 "FEEDS" | "CONTAINS" | "NEXT" | "PART_OF"

interface GraphNode { id: string; label: NodeLabel; properties: Record<string, unknown> }
interface GraphEdge { id: string; type: EdgeType; source: string; target: string; properties: Record<string, unknown> }
interface LogicPack { nodes: GraphNode[]; edges: GraphEdge[]; snippets: Record<string, string> }
interface MutationTimeline { origin: GraphNode; mutations: GraphEdge[]; reads: GraphEdge[]; passes: GraphEdge[]; feeds: GraphEdge[]; terminal: GraphNode | null }
```

---

## 7. Mono-repo Structure

Single repo. No workspaces (yarn/pnpm workspaces or npm workspaces) — backend and frontend are independent runtimes. The root just holds shared config and the `Makefile`.

```
bumblebee_ide/
    backend/
        pyproject.toml       # uv project
        .python-version      # 3.12
        app/
        tests/
    frontend/
        package.json
        tsconfig.json
        tailwind.config.ts
        vite.config.ts
        src/
    docker/
        docker-compose.yml
    docs/
    Makefile
    .env.example
    .gitignore
```

Root `Makefile` targets:
```makefile
up:     docker compose -f docker/docker-compose.yml up -d
down:   docker compose -f docker/docker-compose.yml down
backend: cd backend && uv run uvicorn app.main:app --reload --port 8000
frontend: cd frontend && npm run dev
lint:   cd backend && uv run pylint --fail-under=9.5 app/ && uv run mypy app/
test:   cd backend && uv run pytest --cov=app --cov-fail-under=80
index:  cd backend && uv run python -m app.cli.index $(REPO)
```

---

## 8. Config & Secrets Management

**Decision: Pydantic Settings v2 + `.env` file**

```python
# backend/app/config.py
from __future__ import annotations
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    backend_port: int = 8000
    falkor_host: str = "localhost"
    falkor_port: int = 6379
    falkor_graph_name: str = "bumblebee"
    watch_path: str = ""
    ollama_host: str = "http://localhost:11434"
    orchestrator_model: str = "qwen2.5-coder:7b"
    cypher_model: str = "qwen2.5-coder:7b"

settings = Settings()
```

- Import `settings` from `app.config` everywhere. Never read `os.environ` directly.
- `.env` is gitignored. `.env.example` is committed and kept in sync with `Settings`.
- No secrets manager for now. Add later if deploying externally.

---

## 9. The "Watched Repo" — How It Gets Set

**Decision: Landing page UI input, persisted to `.env`-equivalent config.**

Flow:
1. On first launch, the frontend detects `WATCH_PATH` is empty.
2. A **landing page** (full-screen, minimal) prompts: *"Enter the path to the repository you want to index."* with a text input and an `Index Repository` button.
3. On submit, `POST /index` is called with `{ "path": "/absolute/path/to/repo" }`.
4. The backend validates the path exists, writes it to the running config (in-memory + persists to `.env`), and starts the indexer.
5. Frontend transitions to the main three-panel layout. An index progress bar (via WebSocket `index:progress` events) shows in the status bar.
6. Path can be changed later via `/settings` page or the `/index` command in the terminal-chat.

The landing page also shows: repo name (derived from directory name), estimated file count, a "Recent repositories" list (stored in browser `localStorage`).

---

## 10. Local LLM Strategy

**Decision: Ollama, model `qwen2.5-coder:7b`**

- **Runtime:** Ollama. It has the simplest local setup, a clean REST API, and native tool-use support for recent models. No llama.cpp or vLLM complexity for now.
- **Orchestrator model:** `qwen2.5-coder:7b` — strong at code reasoning, tool use, and instruction following. Small enough to run on a MacBook Pro M-series with < 8GB VRAM.
- **Cypher specialist:** Same model to start (`qwen2.5-coder:7b`). Swap to a fine-tuned Cypher model (e.g., a LoRA on top of Qwen) when/if the vanilla model's Cypher quality is insufficient. The architecture supports this without code changes — just update `CYPHER_MODEL` in `.env`.
- **Cloud fallback:** The `ModelAdapter` interface (see `styling.md` Section 6.3) supports Anthropic and OpenAI. Set `ORCHESTRATOR_MODEL=claude-3-5-sonnet-20241022` and add `ANTHROPIC_API_KEY` to `.env` to switch.
- **Tool-use format:** Ollama's `/api/chat` endpoint supports the OpenAI-compatible `tools` array. Use this format for all adapters so the tool definition schema is identical regardless of provider.

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

See `docs/tickets.md` for the full 800-series backlog with acceptance criteria.

---

## 12. VFS Compose & Virtual Script Architecture (900-Series)

See `docs/vfs_compose_plan.md` for the full design document.

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
