# Technology Stack & Infrastructure Decisions

Technology choices, configuration, infrastructure, and project structure decisions.

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
| FastAPI backend       | `8111` | `uvicorn app.main:app --reload`          |
| Vite frontend         | `5173` | Vite default, do not change              |
| FalkorDB              | `6379` | Redis-compatible port                    |
| WebSocket (backend)   | `8111` | Same process as FastAPI via `/ws` path   |

`.env.example`:
```
BACKEND_PORT=8111
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
| **Styling**        | Tailwind CSS v4           | User specified. Use CSS variables (from `design.system.md`) as Tailwind theme tokens.  |
| **State**          | Zustand                   | Lightweight, no boilerplate, works well alongside React Flow's internal state.   |
| **Graph canvas**   | React Flow v12            | See `arch.core.md` Section 5 for Cytoscape analysis.                            |
| **Data fetching**  | TanStack Query (React Query v5) | Caching, background refetch, WebSocket integration via `queryClient.invalidate`. |
| **Icons**          | Lucide React              | Minimal, consistent with the monospace aesthetic.                                |

`tsconfig.json` flags: `"strict": true`, `"noUncheckedIndexedAccess": true`, `"exactOptionalPropertyTypes": true`.

No CSS Modules, no styled-components, no Emotion. Tailwind only. Custom design tokens from `design.system.md` go in `tailwind.config.ts` as theme extensions.

---

## 6. API Contract (Frontend ↔ Backend)

Base URL: `http://localhost:8111/api/v1`

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
backend: cd backend && uv run uvicorn app.main:app --reload --port 8111
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

    backend_port: int = 8111
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
- **Cloud fallback:** The `ModelAdapter` interface (see `arch.agent-model.md` Section 6.3) supports Anthropic and OpenAI. Set `ORCHESTRATOR_MODEL=claude-3-5-sonnet-20241022` and add `ANTHROPIC_API_KEY` to `.env` to switch.
- **Tool-use format:** Ollama's `/api/chat` endpoint supports the OpenAI-compatible `tools` array. Use this format for all adapters so the tool definition schema is identical regardless of provider.
