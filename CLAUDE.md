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
        services/          # Business logic
        models/            # Pydantic schemas & DB models
        graph/             # FalkorDB queries & Logic Pack builders
        utils/             # Reusable utilities
    tests/
        conftest.py
        test_*.py
frontend/                  # Vite/React app
docker/                    # Docker configs
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

All architecture decisions are documented in `docs/decisions.md`. Key points:

- **Build order:** Phase 1 (backend): 101→102→103→201→202→203→204. Phase 2 (frontend): 301→302→401→402. Phase 3 (AI): 501→502. Phase 4 (live sync): 601→602.
- **React Flow v12** — not v11, not Cytoscape. Custom node/edge types are React components.
- **Ollama** for local LLM with OpenAI-compatible tool-use format. Cloud fallback via `ModelAdapter` interface.
- **Pydantic Settings v2** for all config. Import `settings` from `app.config`. Never read `os.environ` directly.
- **FalkorDB** singleton client via FastAPI lifespan. Graph name: `bumblebee`.
- **No CSS Modules/styled-components** — Tailwind only. Design tokens from `docs/styling.md`.
- **`uv`** for all Python env/dependency management. No `pip` directly.
