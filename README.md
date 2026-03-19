# Bumblebee

**Don't ping a server to piece together your answer. Query a graph of code and let it assemble the answer for you.**

Bumblebee is a **code intelligence infrastructure layer** that transforms codebases into structured, queryable knowledge graphs. Instead of AI agents reading files one at a time — guessing what to read next, missing branches, burning tokens — they query a graph that returns the complete answer in a single operation.

The core innovation is **Atomic GraphRAG**: pre-processed subgraphs ("Logic Packs") that give any LLM the precise context it needs — nothing more, nothing less. One query replaces dozens of file reads. 10-20x fewer tokens. Guaranteed complete traversal. Milliseconds instead of seconds.

Bumblebee ships with an IDE surface that makes the graph visible — you can see call paths, variable mutation timelines, and Logic Packs assembled in real time. But the real product is the intelligence layer underneath: a structured code graph that any agent framework, AI coding tool, or enterprise platform can query.

## Architecture

```
                    ┌─────────────┐
                    │  Source Code │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  tree-sitter │  AST extraction
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  FalkorDB   │  Code graph (nodes + edges + variables)
                    │  (GraphBLAS)│  Sub-100ms Cypher queries at 100k+ nodes
                    └──────┬──────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
  ┌──────▼──────┐   ┌─────▼──────┐   ┌──────▼──────┐
  │ Logic Pack  │   │    VFS     │   │  IDE Demo   │
  │ API         │   │ Projection │   │  Surface    │
  │ (agent      │   │ (git-tracked│   │ (graph +    │
  │  context)   │   │  .py files)│   │  Monaco +   │
  └─────────────┘   └────────────┘   │  terminal)  │
                                     └─────────────┘
```

### Why a graph, not files?

| | MCP / File-based Agent | Bumblebee Graph |
|---|---|---|
| "How does auth flow request → DB?" | 8+ sequential file reads | 1 Cypher query |
| Token cost | ~16,000 (2K per hop) | ~3,000 (single Logic Pack) |
| Missed branches | Common (agent stops early) | Impossible (graph is exhaustive) |
| Latency | Seconds (sequential round trips) | Milliseconds (single query) |
| At 10K queries/day | $500K/mo in API costs | $50K/mo or less |

## Tech Stack

![Python 3.12](https://img.shields.io/badge/Python-3.12-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115-009688)
![React 18](https://img.shields.io/badge/React-18-61DAFB)
![TypeScript](https://img.shields.io/badge/TypeScript-Strict-3178C6)
![FalkorDB](https://img.shields.io/badge/FalkorDB-Graph-red)
![tree-sitter](https://img.shields.io/badge/tree--sitter-AST-green)

- **Backend:** Python 3.12, FastAPI, FalkorDB, tree-sitter, watchdog
- **Frontend:** Vite, React 18, TypeScript (strict), React Flow v12, Monaco Editor, Zustand, Tailwind CSS v4
- **LLM Runtime:** Ollama (default: `qwen2.5-coder:7b`), OpenAI-compatible tool-use format
- **Infrastructure:** Docker Compose (FalkorDB), `uv` (Python), npm (frontend)

## Prerequisites

- **Python 3.12+** — install via `brew install python@3.12` or [python.org](https://www.python.org/)
- **uv** — `curl -LsSf https://astral.sh/uv/install.sh | sh` (Python package manager)
- **Node.js 18+** — install via `brew install node` or [nodejs.org](https://nodejs.org/)
- **Docker** — install [Docker Desktop](https://www.docker.com/products/docker-desktop/) (required for FalkorDB)
- **Ollama** (optional) — `brew install ollama` for local LLM support; the AI chat works with a MockAdapter without it

## Getting Started

### 1. Start FalkorDB

FalkorDB is the graph database that stores the codebase graph. Docker will auto-pull the image on first run.

```bash
make up
```

This starts FalkorDB on `localhost:6379`. Verify with:

```bash
docker ps | grep falkordb
```

### 2. Install and start the backend

```bash
cd backend
uv sync                # install Python dependencies
cd ..
make backend           # starts FastAPI on http://localhost:8000
```

The backend serves the REST API and WebSocket endpoint. Verify it's running:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

### 3. Install and start the frontend

In a new terminal:

```bash
cd frontend
npm install            # install Node dependencies (first time only)
cd ..
make frontend          # starts Vite dev server on http://localhost:5173
```

Open **http://localhost:5173** in your browser.

### 4. Index a repository

On the landing page, enter the absolute path to a Python repository and click **Index Repository**. This parses all `.py` files, extracts the graph structure, and stores it in FalkorDB.

You can also index via the API:

```bash
curl -X POST http://localhost:8000/api/v1/index \
  -H "Content-Type: application/json" \
  -d '{"path": "/absolute/path/to/your/python/repo"}'
```

### 5. (Optional) Start Ollama for AI chat

If you want the NL-to-Cypher AI chat to use a real model instead of the MockAdapter:

```bash
ollama pull qwen2.5-coder:7b
ollama serve                     # starts on http://localhost:11434
```

The chat panel will auto-detect available models.

## Development Commands

```bash
# Infrastructure
make up                # start FalkorDB (Docker)
make down              # stop FalkorDB

# Backend
make backend           # run FastAPI dev server with hot reload (:8000)
make test              # run pytest with coverage (≥80%)
make lint              # black + isort + pylint checks
make format            # auto-format with black + isort

# Frontend
make frontend          # run Vite dev server (:5173)
cd frontend && npm run build      # production build
cd frontend && npm run typecheck  # tsc --noEmit
cd frontend && npm run lint       # ESLint

# Single test file
cd backend && uv run pytest tests/test_roundtrip.py -v
```

## API Endpoints

### 800-Series (Code-as-Data)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/nodes` | Create a LogicNode |
| `GET` | `/api/v1/nodes` | Search/list LogicNodes (`?query=`, `?kind=`, `?limit=`) |
| `GET` | `/api/v1/nodes/{id}` | Get a LogicNode by UUID |
| `PATCH` | `/api/v1/nodes/{id}` | Update a LogicNode |
| `DELETE` | `/api/v1/nodes/{id}` | Deprecate a LogicNode |
| `GET` | `/api/v1/nodes/{id}/edges` | Get edges for a node (`?direction=`, `?types=`) |
| `GET` | `/api/v1/nodes/{id}/variables` | Get variables for a node |
| `POST` | `/api/v1/edges` | Add an edge |
| `DELETE` | `/api/v1/edges` | Remove an edge |
| `GET` | `/api/v1/edges/all` | List all edges |
| `GET` | `/api/v1/variables/{id}/timeline` | Mutation timeline |
| `GET` | `/api/v1/variables/search` | Search variables |
| `GET` | `/api/v1/variables/trace` | Trace a variable |
| `POST` | `/api/v1/import/directory` | Import a directory of Python files |
| `POST` | `/api/v1/import/file` | Import a single file |
| `POST` | `/api/v1/flows` | Create a flow |
| `GET` | `/api/v1/flows` | List all flows |
| `GET` | `/api/v1/flows/{id}` | Get a flow |
| `GET` | `/api/v1/flows/gaps` | Gap analysis report |
| `GET` | `/api/v1/vfs/{module}` | Get VFS-projected source |
| `POST` | `/api/v1/vfs/project` | Trigger full VFS projection |
| `POST` | `/api/v1/vfs/sync` | Sync VFS changes to graph |
| `GET` | `/api/v1/graph-overview` | Overview nodes + edges |

### Legacy (pre-800)

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/index` | Index a repository |
| `GET` | `/api/v1/graph/nodes` | List nodes (paginated) |
| `POST` | `/api/v1/query` | Execute raw Cypher |
| `GET` | `/api/v1/logic-pack/{id}` | Get a Logic Pack subgraph |
| `GET` | `/api/v1/file` | Serve file content for Monaco |
| `POST` | `/api/v1/codegen/{module}` | Generate Python source from graph |
| `POST` | `/api/v1/edit/preview` | Ghost preview of an edit |
| `POST` | `/api/v1/edit/apply` | Apply a previewed edit |
| `POST` | `/api/v1/chat` | AI chat (SSE streaming) |
| `WS` | `/ws/graph` | Real-time graph events |

## Environment Variables

Copy `.env.example` to `.env` and adjust as needed:

| Variable | Default | Description |
|----------|---------|-------------|
| `BACKEND_PORT` | `8000` | FastAPI port |
| `FALKOR_HOST` | `localhost` | FalkorDB host |
| `FALKOR_PORT` | `6379` | FalkorDB port |
| `FALKOR_GRAPH_NAME` | `bumblebee` | Graph database name |
| `WATCH_PATH` | (empty) | Auto-watch repo path for live sync |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama API endpoint |
| `ORCHESTRATOR_MODEL` | `qwen2.5-coder:7b` | Model for AI chat |
| `CYPHER_MODEL` | `qwen2.5-coder:7b` | Model for NL-to-Cypher |

## Current Status

### Core Infrastructure — Complete

The code-as-data architecture is fully functional. A Python codebase can be imported, represented as a knowledge graph, queried via Cypher, and projected back to editable files.

- **Graph engine:** FalkorDB with GraphBLAS, sub-100ms queries, 100k+ node capacity
- **Import pipeline:** Python source → tree-sitter AST → LogicNodes + Variables + Edges
- **Identity system:** UUID7 (stable keys) + SHA-256 AST hash (dedup detection)
- **Logic Packs:** Pre-processed subgraphs for LLM consumption via API
- **Variable mutation tracing:** Full lifecycle queries across function/file boundaries
- **Bidirectional VFS:** Graph → git-tracked `.py` files → edits sync back to graph
- **Graph serialization:** `.bumblebee/` directory with JSON nodes/edges, human-readable Git diffs
- **Agent tools:** 17 OpenAI-compatible function-calling tools for graph query and mutation
- **Flow engine:** Composable, hierarchical flows with promote-to-LogicNode capability
- **Gap analysis:** Dead-ends, orphans, circular deps, untested mutations

### IDE Demo Surface — Functional

- Sigma.js knowledge graph canvas with ForceAtlas2 layout
- Monaco editor with multi-tab compose surface
- Terminal chat with NL-to-Cypher and VFS query support
- Semantic diff visualization

### Next

- Multi-language support (TypeScript next)
- Logic Pack benchmark (graph-backed agent vs. file-based agent)
- Standalone API packaging for integration with external agent frameworks

## Documentation

- [Architecture Decisions](docs/decisions.md)
- [Graph Schema Specification](docs/schema.md)
- [Ticket Backlog](docs/tickets.md)
- [Coding Standards](docs/coding_standards.md)
- [Styling Guide](docs/styling.md)
- [Code Generation Limitations](docs/codegen-limitations.md)
- [Manifesto](docs/manifesto.md)

## License

Private — All rights reserved.
