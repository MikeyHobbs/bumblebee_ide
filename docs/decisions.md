# Architecture Decisions: Bumblebee IDE

Answers to all open questions that would otherwise block Claude Code or cause inconsistent code generation.

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

The natural dependency chain is:

```
TICKET-101 (scaffold)
    └── TICKET-102 (AST structural nodes)
        └── TICKET-103 (AST relationship edges)
            └── TICKET-201 (variable nodes)
                └── TICKET-202 (mutation/read edges)
                    └── TICKET-203 (PASSES_TO cross-function)
                        └── TICKET-204 (mutation timeline query + endpoint)
                            ├── TICKET-501 (full query template library)
                            │   └── TICKET-502 (NL -> Cypher agent)
                            ├── TICKET-301 (graph canvas)
                            │   └── TICKET-302 (Logic Pack visualizer)
                            │       └── TICKET-401 (Monaco context manager)
                            │           └── TICKET-402 (bidirectional highlighting)
                            └── TICKET-601 (file watcher)
                                └── TICKET-602 (ghost preview)
```

**Phase 1 (backend core):** 101 → 102 → 103 → 201 → 202 → 203 → 204. This gives a fully functional graph with mutation tracking and a queryable API. No frontend needed to validate correctness.

**Phase 2 (frontend + graph viz):** 301 → 302 → 401 → 402. Wire the graph canvas and Monaco to the Phase 1 API.

**Phase 3 (AI layer):** 501 → 502. Build the query library and NL agent on top of the validated graph.

**Phase 4 (live sync + agent):** 601 → 602. File watcher and ghost preview are the final integration layer.
