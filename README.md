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

## Quick Start

```bash
# Start FalkorDB
make up

# Install backend dependencies & run
cd backend && uv sync
make backend          # FastAPI on :8000

# Install frontend dependencies & run
cd frontend && npm install
make frontend         # Vite on :5173

# Run tests
make test

# Lint & typecheck
make lint
```

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
- [ ] TICKET-206: Code Generator — Graph to Python
- [ ] TICKET-207: Round-Trip Integrity Tests

### Phase 3: Frontend + Graph Viz
- [ ] TICKET-301: Global Force-Directed Canvas
- [ ] TICKET-302: Logic Pack Visualizer + Function Flow View
- [ ] TICKET-303: Execution Flow Explorer
- [ ] TICKET-401: Monaco Context Manager
- [ ] TICKET-402: Bidirectional Highlighting & Mutation Gutter
- [ ] TICKET-403: Graph-Based Code Editing

### Phase 4: AI Layer
- [ ] TICKET-501: Atomic Retrieval Query Templates
- [ ] TICKET-502: Natural Language to Cypher Agent

### Phase 5: Live Sync
- [ ] TICKET-601: File System Watcher
- [ ] TICKET-602: Agent Ghost Preview

## Documentation

- [Architecture Decisions](docs/decisions.md)
- [Ticket Backlog](docs/tickets.md)
- [Coding Standards](docs/coding_standards.md)
- [Styling Guide](docs/styling.md)
- [Manifesto](docs/manifesto.md)

## License

Private — All rights reserved.
