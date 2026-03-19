# Manifesto: Bumblebee — Code as Data

## 1. The Core Thesis

**Code is data. Files are views. The graph is the source of truth.**

**Don't ping a server to piece together your answer. Query a graph of code and let it assemble the answer for you.**

Today, every AI agent that touches code does the same thing: it reads files one at a time, guesses which file to read next, and hopes it followed the right thread. An agent answering "how does authentication flow from request to database?" makes 8+ sequential tool calls — search, read, search, read, search, read — each with latency, token overhead, and the risk of missing a branch. It is reconstructing a graph by crawling text. Badly.

Bumblebee eliminates this entirely. The codebase already exists as a structured, queryable knowledge graph. One query returns the complete answer — every node, every edge, every code snippet in the path. No round trips. No missed branches. No wasted tokens.

This is not a better way to *browse* code. It is a fundamentally different substrate for AI agents to *reason about* code.

### The Inversion

In the age of Agentic AI, the fundamental unit of software is not a file — it is a *logic node*: a function, a method, a class. These nodes exist in a knowledge graph, connected by typed relationships that capture how logic flows, how data mutates, and how contracts are fulfilled. Files are merely one possible *projection* of this graph — a human-readable serialization optimized for compilers and text editors.

Bumblebee inverts the traditional relationship between code and its representation. Instead of parsing files into a graph for visualization, it treats the graph as canonical and projects files on demand:

- **AI agents create and edit LogicNodes**, not text files. The graph handles identity, deduplication, and dependency tracking.
- **Humans read projected files** in a virtual filesystem (VFS), using familiar tools — editors, linters, debuggers — on output that is regenerated from the graph.
- **Git stores the serialized graph** as JSON files, giving human-readable diffs and standard version control.

### The Question That Matters

The hardest question in any large codebase is not "where is this function?" but **"what happens to this data?"** A variable is created, passed through arguments, mutated by methods, aliased into new names, and eventually consumed — often across dozens of functions. No existing tool makes that journey visible. Bumblebee does — in one query, in milliseconds.

## 2. The Two-Tier Node Model

Bumblebee's graph has two tiers of nodes, each optimized for a different kind of query.

### Tier 1: Logic Nodes — Units of Logic

LogicNodes are the atomic units that agents and humans *author*. A LogicNode is a function, method, class, constant, or type alias. Each has:

- A **stable UUID** (primary key) — edges never need remapping when code is edited.
- An **AST hash** (SHA-256 of canonical AST) — catches duplicates automatically.
- A **semantic intent** — a one-line natural language description of what the node does, generated or authored.
- **Source text** — the actual code, stored as a property on the node.
- **Formal signature** — parameters, return type, decorators — the node's contract with the outside world.

LogicNodes are what agents create, query, modify, and reason about. They are the currency of the knowledge graph.

### Tier 2: Variable Nodes — Units of Data Flow

Variables are the atomic units that agents *trace*. They exist as separate graph nodes because their purpose is to be tracked *across* LogicNode boundaries. A variable is created in one function, passed to another, mutated in a third, read in a fourth.

The **mutation timeline query** — Bumblebee's killer feature — requires variables as first-class nodes. Starting from any Variable node, traverse ASSIGNS → MUTATES → PASSES_TO → READS edges recursively to reconstruct the variable's full lifecycle across the entire codebase.

### What's NOT a Node

Statements and control flow structures are *internal* to a LogicNode's AST. Agents don't query "find all if-statements" — they query functions and variables. The VFS projection handles rendering control flow for humans. This keeps the graph focused on the queries that matter.

## 3. Technical Pillars

### 3.1 Graph as Source of Truth — Bidirectional Sync

The FalkorDB graph is the canonical representation, but the VFS projection is a **git-tracked, editable view** — not a throwaway artifact. This creates a bidirectional sync model:

- **VFS files** (`.bumblebee/vfs/`) — real `.py` files projected from the graph, **committed to Git**. Existing compilers, linters, and debuggers work unchanged. Edits to VFS files flow back to the graph via the reverse pipeline.
- **Serialized JSON** (`.bumblebee/nodes/`, `.bumblebee/edges/`) — committed to Git. Human-readable diffs, standard tooling.
- **Editor views** — Monaco displays VFS files. Edits flow back through the graph.

The VFS is git-tracked because the projected files are the artifact that humans, CI systems, and external tools actually consume. Tracking them means PRs show real Python diffs alongside graph diffs, and contributors who don't use Bumblebee can still read and edit the code — their changes are imported back into the graph on the next sync.

### 3.2 Variable Mutation Tracking — The Core Differentiator

Every variable is a first-class node in the graph. When a LogicNode is created or updated, Bumblebee automatically extracts:

- **Assignment sites** — where a variable is created or re-bound (`x = …`, `self.x = …`). Creates `ASSIGNS` edges.
- **Mutation sites** — where its state changes in place (`.append()`, `[key] = …`, `+=`). Creates `MUTATES` edges.
- **Read sites** — where it is consumed without modification. Creates `READS` edges.
- **Pass-through sites** — where it is handed to another function as an argument, creating a `PASSES_TO` edge that links the caller's variable to the callee's parameter.
- **Return sites** — where it is yielded or returned from a function. Creates `RETURNS` edges.
- **Feed sites** — where a read of one variable feeds into the assignment of another within the same function. Creates `FEEDS` edges.

A single Cypher query returns the **full mutation timeline** of any variable: from its origin, through every transformation, to its final consumption — across function and file boundaries. This is the query that no text-based search can replicate.

### 3.3 Atomic GraphRAG — Query the Graph, Assemble the Answer

This is the core of what makes Bumblebee an infrastructure layer, not just a visualization tool.

Today's AI coding tools — whether they use MCP servers, file-reading tools, or RAG over chunked source — all share the same fundamental limitation: **the agent pieces together its understanding one request at a time.** It reads a file, decides what to read next, reads that, backtracks, reads something else. Each step is a network round trip, a token cost, and a chance to miss something. Complex questions about a codebase require dozens of these sequential hops. The agent is manually traversing a graph that doesn't exist.

Bumblebee makes the graph exist. And instead of feeding an LLM raw source text, it feeds **"Logic Packs"** — pre-processed subgraphs containing only the LogicNodes relevant to a specific query. The graph assembles the complete, precise context in a single operation:

- **"What services touch PII?"** — one Cypher query, not an agent grepping 10,000 files
- **"What's the blast radius of changing this schema?"** — traverse DEPENDS_ON edges, not guessing at imports
- **"How does auth flow from request to database?"** — complete call path in milliseconds, not 8+ sequential reads
- **"Where is this config value actually used at runtime?"** — variable mutation trace across every function boundary

A Logic Pack for a variable mutation query includes every function that touches the variable, the edges between them, and the relevant source snippets — nothing more. This gives small local models (7B–8B) the same effective context as a 100B model working from raw files.

**The performance difference is not marginal — it is structural.** An MCP-based agent making 8 round trips at 2,000 tokens each consumes 16,000 tokens and takes seconds. Bumblebee returns the same answer in one query at ~3,000 tokens in milliseconds. At enterprise scale (10,000+ agent queries per day), this translates to 10-20x reduction in LLM API cost and dramatically higher accuracy because the graph traversal is exhaustive — it never misses a branch.

### 3.4 Graph-to-Git Serialization

The graph serializes to a `.bumblebee/` directory structure:

```
.bumblebee/
  meta.json                        # Graph version, node/edge/variable counts
  nodes/
    <uuid>.json                    # One file per LogicNode
  variables/
    var_<scope_hash>.json          # Variable nodes grouped by scope
  edges/
    manifest.json                  # All edges in one file
  flows/
    flow_<name>.json               # Named end-to-end processes
  vfs/                             # Git-tracked — human-readable projections
    services/auth.py               #   editable, changes sync back to graph
    models/user.py
```

Both the JSON graph data and the VFS files are committed to Git. This gives two complementary views in every PR: the structural graph diff (which nodes/edges changed) and the familiar Python diff (what the code looks like). The VFS is not a build artifact — it's a first-class, editable representation of the graph.

### 3.5 Composable Flows — Hierarchy of Calls

Flows are not just documentation — they are **reusable, composable units of logic**. A flow is an ordered sequence of LogicNode calls that represents an end-to-end process. Crucially:

- **Flows can contain sub-flows.** A "process order" flow might include a "validate payment" sub-flow and a "ship inventory" sub-flow. This creates a hierarchy: Flow → sub-flows → LogicNodes.
- **Flows can become LogicNodes.** When a flow matures into a stable, reusable process, it can be promoted to a LogicNode (`kind: "flow_function"`) that calls all its constituent nodes. This bridges the gap between curated understanding (flow) and executable code (function).
- **Flows are first-class in Git.** Each flow is a named JSON file in `.bumblebee/flows/`, versioned and diffable. In scientific computing and data pipelines, flows represent reproducible processes that must be tracked, shared, and composed.

The `CONTAINS_FLOW` edge connects a parent flow to its sub-flows. The `STEP_OF` edge connects LogicNodes to the flows they participate in. Together, these edges represent the full call hierarchy — from high-level workflows down to individual functions.

### 3.6 Agent-Native Interface

Agents interact with the graph through typed tools, not file I/O:

- **Query tools** find nodes, trace variables, get Logic Packs, discover gaps.
- **Mutation tools** create/update/deprecate nodes, add/remove edges, define flows.
- **The agent never reads or writes files directly.** It operates on the graph; the VFS projection handles file output.

This eliminates entire categories of agent errors: merge conflicts, partial writes, inconsistent formatting, lost context. The graph enforces structural invariants that raw text cannot.

## 4. Engineering Objectives

- **Scalability:** Support 100k+ LogicNodes using FalkorDB's GraphBLAS (sparse matrix) engine to maintain sub-100ms query times. Variable nodes increase node count; the schema ensures mutation queries remain bounded by hop depth, not total graph size.
- **Transparency:** Eliminate "Black Box" AI code generation by visualizing proposed changes on the graph before they are committed. When an agent proposes a change that mutates a variable, the graph shows every downstream consumer that will be affected.
- **Efficiency:** Use small local models (7B–8B parameters) for complex reasoning by providing them with high-density, low-noise Logic Packs. A mutation-aware Logic Pack is typically 10–50x smaller than the raw files it spans.
- **Correctness:** Variable graphs are re-derived from the LogicNode's AST on every update — they are never stale. The UUID-based identity system means edges stay stable across edits.
- **Deduplication:** The AST hash catches identical logic automatically. Create a function that already exists? The system warns you and points to the existing node.

## 5. The Infrastructure Layer

Bumblebee is not an IDE — it is a **code intelligence infrastructure layer** with an IDE as its demo surface.

The IDE makes the invisible visible: you can *see* the graph, *see* the mutation trace, *see* the Logic Pack assembled in real time. But the real product is what sits behind it — a structured, queryable code graph that any agent framework, any AI coding tool, any enterprise platform can query.

**Any system that has AI agents reasoning about code can benefit from this layer:**

- Agent platforms (LangChain, CrewAI, custom frameworks) get structured code context instead of file-crawling
- AI coding tools (Copilot, Cursor, Claude Code) get complete, token-efficient subgraphs instead of naive context stuffing
- Enterprise security tools get variable-level dataflow analysis instead of pattern matching on text
- CI/CD systems get graph-aware impact analysis — "which tests need to re-run given this change?" is a graph query

The graph doesn't replace these tools. It makes all of them dramatically better.

## 6. What Makes This Different

| Capability | Traditional IDE | Static Analysis | MCP / File-based Agent | Bumblebee |
|-----------|----------------|-----------------|------------------------|-----------|
| "Go to definition" | Yes | Yes | N/A | Yes |
| "Find all references" | Yes | Yes | Grep | Graph query |
| Cross-file call graph | No | Partial | No | Visual + queryable |
| Variable mutation timeline | No | No | No | First-class graph query |
| AI context from graph | No | No | No | Logic Packs |
| Agent creates logic, not files | No | No | No | Yes — LogicNode CRUD |
| Semantic diff of changes | No | No | No | Graph diff |
| Deduplication detection | No | No | No | AST hash matching |
| Live visual diff of agent changes | No | No | No | Ghost Preview |
| Complex question in 1 query | No | Partial | 8+ round trips | Single Cypher query |
| Token cost for agent context | N/A | N/A | 16,000+ tokens | ~3,000 tokens |
| Guaranteed complete traversal | N/A | Yes | No (agent may stop early) | Yes (graph is exhaustive) |
