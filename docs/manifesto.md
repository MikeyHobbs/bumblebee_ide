# Manifesto: Bumblebee IDE

## 1. The Core Thesis
In the age of Agentic AI, codebases grow faster than human cognitive limits. Traditional text-based IDEs are "flat" and fail to visualize the ripple effects of AI-generated changes. Bumblebee IDE is a **Visual Logic Engine** that treats the codebase as a living graph, making architectural impact immediately visible.

The hardest question in any large codebase is not "where is this function?" but **"what happens to this data?"** A variable is created, passed through arguments, mutated by methods, aliased into new names, and eventually consumed—often across dozens of files. No existing tool makes that journey visible. Bumblebee does.

## 2. Technical Pillars

### 2.1 Graph as Interface
The primary way to navigate a giant repo is through logical relationships, not file folders. The graph encodes structural edges (`CALLS`, `INHERITS`, `IMPORTS`) **and** data-flow edges (`ASSIGNS`, `MUTATES`, `READS`, `PASSES_TO`). This dual-layer model lets a developer ask both *"who calls this function?"* and *"what touches this variable before it reaches the database?"*

### 2.2 Variable Mutation Tracking — The Core Differentiator
Every variable is a first-class node in the graph. When code is parsed, Bumblebee extracts:
* **Assignment sites** — where a variable is created or re-bound (`x = …`, `self.x = …`).
* **Mutation sites** — where its state changes in place (`.append()`, `[key] = …`, `+=`).
* **Read sites** — where it is consumed without modification.
* **Pass-through sites** — where it is handed to another function as an argument, creating a `PASSES_TO` edge that links the caller's variable node to the callee's parameter node.

A single Cypher query can then return the **full mutation timeline** of any variable: from its origin, through every transformation, to its final consumption—across function and file boundaries. This is the query that no text-based search can replicate.

### 2.3 Atomic GraphRAG
Intelligence lives in the database. Instead of feeding an LLM raw source text, we feed it **"Logic Packs"**—pre-processed subgraphs containing only the code relevant to a specific logic chain. A Logic Pack for a variable mutation query, for example, would include every function that touches the variable, the edges between them, and the relevant source snippets—nothing more. This gives small local models (7B–8B) the same effective context as a 100B model working from raw files.

### 2.4 Zero-Latency Sync
A bidirectional link between FalkorDB (the source of truth) and Monaco (the execution layer):
* **Graph → Editor:** Click a node or a mutation site; Monaco jumps to the exact line.
* **Editor → Graph:** Move the cursor into a function; the graph highlights the node and pulses its edges. Edit a line; the watcher re-indexes only the affected file and the graph updates in real time.

## 3. Graph Schema (Node & Edge Model)

### Nodes
| Label | Key Properties | Description |
|-------|---------------|-------------|
| `Module` | `path`, `name`, `checksum` | A single source file |
| `Class` | `name`, `start_line`, `end_line`, `module_path` | A class definition |
| `Function` | `name`, `start_line`, `end_line`, `params`, `return_type` | A function or method |
| `Variable` | `name`, `scope`, `origin_line`, `origin_func` | A tracked variable or attribute |

### Edges
| Type | From → To | Description |
|------|-----------|-------------|
| `DEFINES` | Module/Class → Function | Containment |
| `CALLS` | Function → Function | Static or dynamic call |
| `INHERITS` | Class → Class | Subclass relationship |
| `IMPORTS` | Module → Module | Import dependency |
| `ASSIGNS` | Function → Variable | Variable creation / re-binding |
| `MUTATES` | Function → Variable | In-place state change |
| `READS` | Function → Variable | Read-only access |
| `PASSES_TO` | Variable → Variable | Argument passing across call boundary |
| `RETURNS` | Function → Variable | A variable that is yielded or returned |

This schema enables the **Mutation Timeline Query**: starting from any `Variable` node, traverse incoming `ASSIGNS`/`MUTATES`/`PASSES_TO` edges recursively to reconstruct the variable's full lifecycle.

## 4. Engineering Objectives

* **Scalability:** Support 100k+ nodes using FalkorDB's GraphBLAS (sparse matrix) engine to maintain sub-100ms query times. Variable nodes will significantly increase node count; the schema is designed so that mutation queries remain bounded by hop depth, not total graph size.
* **Transparency:** Eliminate "Black Box" AI code generation by visualizing proposed changes on the graph before they are committed. When an agent proposes a change that mutates a variable, the graph shows every downstream consumer that will be affected.
* **Efficiency:** Use small local models (7B–8B parameters) for complex reasoning by providing them with high-density, low-noise Logic Packs. A mutation-aware Logic Pack is typically 10–50× smaller than the raw files it spans.
* **Correctness:** The mutation graph is re-derived from the AST on every save—it is never stale. Partial re-indexing ensures only changed files are reprocessed, keeping the feedback loop under 500 ms for typical edits.

## 5. What Makes This Different

| Capability | Traditional IDE | Static Analysis (e.g. Pyright) | Bumblebee IDE |
|-----------|----------------|-------------------------------|---------------|
| "Go to definition" | ✅ | ✅ | ✅ |
| "Find all references" | ✅ | ✅ | ✅ |
| Cross-file call graph | ❌ | Partial | ✅ Visual + queryable |
| Variable mutation timeline | ❌ | ❌ | ✅ First-class graph query |
| AI context from graph | ❌ | ❌ | ✅ Logic Packs |
| Live visual diff of agent changes | ❌ | ❌ | ✅ Ghost Preview |
