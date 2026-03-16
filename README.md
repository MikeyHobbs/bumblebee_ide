# Bumblebee IDE

**A Visual Logic Engine that treats codebases as living graphs.**

Bumblebee transforms source code into an interactive, queryable graph — visualizing architectural relationships (CALLS, INHERITS, USES, MUTATES) and enabling developers to trace variable lifecycles, understand mutation impact, and navigate code logic visually. The core innovation is **Atomic GraphRAG**: feeding LLMs pre-processed subgraphs ("Logic Packs") instead of raw text.

## Architecture

```
                    ┌─────────────┐
                    │  Source Code │
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  tree-sitter │  AST Parser
                    │  AST Parser  │  (Structural + Relationship)
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
                    │  FalkorDB   │  Graph Database
                    │  (GraphBLAS)│  (Nodes + Edges)
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
       ┌──────▼──────┐ ┌──▼───┐ ┌──────▼──────┐
       │  React Flow  │ │Monaco│ │  Terminal /  │
       │  Graph Canvas│ │Editor│ │  AI Chat     │
       └─────────────┘ └──────┘ └─────────────┘
```

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

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/v1/index` | Index a repository |
| `POST` | `/api/v1/index/file` | Re-index a single file |
| `GET` | `/api/v1/graph/nodes` | List nodes (paginated, filterable by label) |
| `GET` | `/api/v1/graph/node/{id}` | Get a single node by name |
| `POST` | `/api/v1/query` | Execute raw Cypher |
| `GET` | `/api/v1/logic-pack/{id}` | Get a Logic Pack subgraph |
| `GET` | `/api/v1/variables/{id}/timeline` | Mutation timeline for a variable |
| `GET` | `/api/v1/variables/search` | Search variables by name |
| `GET` | `/api/v1/file` | Serve file content for Monaco |
| `POST` | `/api/v1/codegen/{module_id}` | Generate Python source from graph |
| `POST` | `/api/v1/codegen/function/{id}` | Generate a single function |
| `PATCH` | `/api/v1/graph/statement/{id}` | Update a statement |
| `POST` | `/api/v1/graph/statement` | Insert a statement |
| `DELETE` | `/api/v1/graph/statement/{id}` | Delete a statement |
| `GET` | `/api/v1/graph/function/{id}/flow` | Function flow subgraph |
| `POST` | `/api/v1/edit/preview` | Ghost preview of an edit |
| `POST` | `/api/v1/edit/apply` | Apply a previewed edit |
| `POST` | `/api/v1/chat` | AI chat (SSE streaming) |
| `GET` | `/api/v1/models` | List available LLM models |
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

## Progress

### Phase 1: Backend Core
- [x] TICKET-101: System Scaffolding
- [x] TICKET-102: AST Parser — Structural Nodes
- [x] TICKET-103: AST Parser — Relationship Edges
- [x] TICKET-104: Statement & Control Flow Nodes
- [x] TICKET-201: Variable & Assignment Nodes
- [x] TICKET-202: Mutation & Read Detection
- [x] TICKET-203: Cross-Function PASSES_TO
- [x] TICKET-205: FEEDS Edges
- [x] TICKET-204: Mutation Timeline Query + Endpoint

### Phase 2: Code Generation
- [x] TICKET-206: Code Generator — Graph to Python
- [x] TICKET-207: Round-Trip Integrity Tests

### Phase 3: Frontend + Graph Viz
- [x] TICKET-301: Global Force-Directed Canvas
- [x] TICKET-302: Logic Pack Visualizer + Function Flow View
- [x] TICKET-303: Execution Flow Explorer
- [x] TICKET-401: Monaco Context Manager
- [x] TICKET-402: Bidirectional Highlighting & Mutation Gutter
- [x] TICKET-403: Graph-Based Code Editing

### Phase 4: AI Layer
- [x] TICKET-501: Atomic Retrieval Query Templates
- [x] TICKET-502: Natural Language to Cypher Agent

### Phase 5: Live Sync
- [x] TICKET-601: File System Watcher
- [x] TICKET-602: Agent Ghost Preview

## Documentation

- [Architecture Decisions](docs/decisions.md)
- [Ticket Backlog](docs/tickets.md)
- [Coding Standards](docs/coding_standards.md)
- [Styling Guide](docs/styling.md)
- [Code Generation Limitations](docs/codegen-limitations.md)
- [Manifesto](docs/manifesto.md)

## License

Private — All rights reserved.
