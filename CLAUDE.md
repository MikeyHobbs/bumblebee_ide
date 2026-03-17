# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Bumblebee IDE is a **Visual Logic Engine** that treats codebases as living graphs. It visualizes architectural relationships (CALLS, INHERITS, USES) using FalkorDB as the graph database, React Flow for visualization, and Monaco for code editing. The core innovation is "Atomic GraphRAG" — feeding LLMs pre-processed subgraphs ("Logic Packs") instead of raw text.

## Tech Stack

- **Backend:** Python 3.12, FastAPI, FalkorDB (graph DB with GraphBLAS engine), tree-sitter (AST parsing), watchdog (file system watcher)
- **Frontend:** Vite, React 18, TypeScript (strict), React Flow v12 (graph canvas), @monaco-editor/react, Zustand (state), Tailwind CSS v4 (styling), TanStack Query v5, D3-force + dagre (layout)
- **LLM Runtime:** Ollama (default model: `qwen2.5-coder:7b`), OpenAI-compatible tool-use format
- **Config:** Pydantic Settings v2 + `.env` file (see `backend/app/config.py`)
- **Infrastructure:** Docker Compose (FalkorDB with optimized memory settings)
- **Package Management:** `uv` for Python (`uv sync`, `uv run`), npm for frontend
- **Target Repo:** Selected via UI landing page text input (no CLI arg)

## Project Structure

```
backend/
    app/
        main.py            # FastAPI entrypoint
        routers/           # API route modules
        services/          # Business logic (organized by domain)
            parsing/       # AST extraction pipeline (ast_parser, extractors)
            persistence/   # Graph ↔ disk (serializer, deserializer, vfs_engine, import_pipeline)
            crud/          # Node/edge/flow CRUD (logic_node_service, edge_service, flow_service)
            codegen/       # Graph → source code (code_generator, write_back)
            agent/         # LLM / tool-use (model_adapter, agent_tools_v2, tool_executor)
            analysis/      # Diffing, gaps, hashing (semantic_diff, gap_analysis, hash_identity)
            watchers/      # File system monitoring (file_watcher, bumblebee_watcher)
        models/            # Pydantic schemas & DB models
        graph/             # FalkorDB queries & Logic Pack builders
        utils/             # Reusable utilities
    tests/
        conftest.py
        test_*.py
frontend/
    src/
        api/               # API hooks (split by domain: graph, nodes, variables, flows, import, files)
        components/        # UI components (organized by role)
            canvas/        # Graph visualization (AtlasOverview, GraphCanvas)
            panels/        # Side panels (CallContextSidebar, LogicPackPanel, SemanticDiff, etc.)
            editor/        # Code editing (CodeEditor, FunctionFlowView)
            chat/          # AI chat (TerminalChat)
            layout/        # App shell (Layout, TabBar, Breadcrumbs)
            pages/         # Full pages (LandingPage)
        store/             # Zustand stores (graphStore, editorStore, layoutStore)
        graph/             # React Flow node/edge types & layout algorithms
        types/             # TypeScript type definitions
docker/                    # Docker configs
docs/                      # Architecture docs, schema spec, tickets
```

## Build & Development Commands

```bash
# Backend (run from backend/ or use Makefile from root)
uv run uvicorn app.main:app --reload --port 8000   # dev server
uv run black . --line-length 120                    # format
uv run isort . --profile black --line-length 120    # sort imports
uv run pylint --fail-under=9.5 app/                 # lint
uv run mypy app/ --strict                           # type check
uv run pytest --cov=app --cov-fail-under=80         # tests
uv run pytest tests/test_specific.py                # single test file
uv run pytest tests/test_specific.py::test_name     # single test function

# Frontend (run from frontend/)
npm install         # install deps
npm run dev         # Vite dev server on :5173
npm run build       # production build
npm run lint        # ESLint
npm run typecheck   # tsc --noEmit

# Infrastructure
docker compose -f docker/docker-compose.yml up -d   # start FalkorDB
docker compose -f docker/docker-compose.yml down     # stop

# Root Makefile shortcuts
make up        # start FalkorDB
make down      # stop FalkorDB
make backend   # run backend dev server
make frontend  # run frontend dev server
make lint      # lint backend
make test      # test backend
```

## Coding Standards

- **PEP 8** with 120-char line length
- **All functions** must have type hints (params + return). Use `from __future__ import annotations` in every module.
- **Google-style docstrings** required on all public modules, classes, functions, and methods.
- **Double quotes** for strings by default.
- **Custom exceptions** inheriting from a project-level base for domain errors. Never bare `except:`.
- Pylint disables only inline on specific lines with justification — never module-level.

## Git Conventions

- Branch naming: `feature/<ticket>-<short-desc>`, `fix/<ticket>-<short-desc>`
- Commit messages: imperative mood, reference ticket ID — e.g., `TICKET-102: Implement incremental AST parser`

## Key Technical Decisions

All architecture decisions are documented in `docs/decisions.md`. Graph schema is in `docs/schema.md`. Key points:

- **Build order (800-series):** Phase 0 (foundation) → Phase 1 (CRUD) → Phase 3 (import) → Phase 2 (serialization) → Phase 4 (VFS) → Phase 5 (flows) → Phase 6 (frontend) → Phase 7 (agent). See `docs/tickets.md` for details.
- **React Flow v12** — not v11, not Cytoscape. Custom node/edge types are React components.
- **Ollama** for local LLM with OpenAI-compatible tool-use format. Cloud fallback via `ModelAdapter` interface.
- **Pydantic Settings v2** for all config. Import `settings` from `app.config`. Never read `os.environ` directly.
- **FalkorDB** singleton client via FastAPI lifespan. Graph name: `bumblebee`.
- **No CSS Modules/styled-components** — Tailwind only. Design tokens from `docs/styling.md`.
- **`uv`** for all Python env/dependency management. No `pip` directly.
