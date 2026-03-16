# Ticket Backlog: Bumblebee IDE Implementation

> **Core principle:** The graph is the canonical representation of code logic. Code is a serialization format. The graph captures enough to reconstruct valid Python, and edits can flow in both directions: Code → Graph and Graph → Code.

---

## Epic 1: Repository & Environment

- [ ] **TICKET-101: System Scaffolding**
    - **Goal:** Establish the mono-repo layout and local dev environment so every subsequent ticket has a runnable baseline.
    - **Tasks:**
        - Create the directory structure: `/backend` (FastAPI + Python 3.12), `/frontend` (Vite + React 18 + TypeScript), `/docker`.
        - Write `docker-compose.yml` with services: `falkordb` (pinned version, tuned `GRAPH.CONFIG` for `THREAD_COUNT`, `CACHE_SIZE`, `MAX_QUEUED_QUERIES`), `backend`, `frontend`.
        - Add a root `Makefile` with targets: `up`, `down`, `lint`, `test`, `index` (runs the AST parser against a target repo).
        - Create `pyproject.toml` with Black, isort, Pylint, mypy config per `coding_standards.md`.
        - Seed a `.env.example` with all required environment variables (`FALKOR_HOST`, `FALKOR_PORT`, `WATCH_PATH`, etc.).
    - **Acceptance Criteria:**
        - `make up` boots all three services; FalkorDB is reachable on `localhost:6379`; FastAPI docs load at `/docs`.
        - `make lint` passes with Pylint >= 9.5 on the (empty) backend package.

- [ ] **TICKET-102: Incremental AST Parser — Structural Nodes** *(amended)*
    - **Goal:** Parse Python source files into `Module`, `Class`, and `Function` nodes with precise source coordinates.
    - **Tasks:**
        - Integrate `tree-sitter-python` via the `tree-sitter` Python bindings.
        - Extract node types: `module`, `class_definition`, `function_definition` (including nested and async variants).
        - For each node, capture: `name`, `start_line`, `end_line`, `start_col`, `end_col`, `params` (for functions), `decorators`, `docstring` (first expression statement if string), `source_text` (full source of the node).
        - Write `MERGE` Cypher templates for upserting `Module`, `Class`, `Function` nodes and `DEFINES` edges.
        - Implement **Partial Re-indexing**: on file change, delete all nodes where `module_path = <changed_file>` and re-create them. Use a `checksum` property on `Module` to skip unchanged files.
    - **Acceptance Criteria:**
        - Given a sample Python repo (~50 files), the parser produces the correct node count matching manual inspection.
        - Re-indexing a single changed file completes in < 200 ms.
        - `DEFINES` edges correctly nest Functions inside Classes inside Modules.
        - Each `Function` node's `source_text` property contains the complete function source (used by code generator in TICKET-207).

- [ ] **TICKET-103: Incremental AST Parser — Relationship Edges** *(amended)*
    - **Goal:** Extract `CALLS`, `INHERITS`, and `IMPORTS` edges from the AST, with execution ordering.
    - **Tasks:**
        - **CALLS:** Walk `call_expression` nodes; resolve the callee name to a `Function` node via scope lookup (local → class → module → imported). Record properties: `call_line`, `seq` (statement position within the enclosing function, top-to-bottom), `call_order` (position among all calls in that function).
        - **INHERITS:** Extract base classes from `class_definition` argument lists; create edges to the resolved `Class` nodes.
        - **IMPORTS:** Parse `import_statement` and `import_from_statement`; create `IMPORTS` edges between `Module` nodes. Store `alias` if present.
    - **Acceptance Criteria:**
        - A test case with known call chains (A → B → C) produces the correct `CALLS` path in FalkorDB.
        - Cross-file imports resolve correctly (e.g., `from app.services.auth import verify_token` links to the right `Function` node).
        - `CALLS` edges within a function are ordered: if `f()` calls `a()` then `b()` then `c()`, the edges have `call_order` 0, 1, 2.

- [ ] **TICKET-104: Statement & Control Flow Nodes** *(new)*
    - **Goal:** Extract every statement within a function body as a graph node, and represent control flow structures as container nodes, so the graph captures the full execution logic.
    - **Tasks:**
        - **Statement nodes:** For each statement in a function body (assignment, expression, return, raise, assert, pass, delete, global, nonlocal), create a `Statement` node with properties:
            - `source_text`: the raw source of the statement
            - `seq`: integer position within the parent (function body or control flow branch), 0-indexed
            - `start_line`, `end_line`, `start_col`, `end_col`
            - `kind`: `assignment | expression | return | yield | raise | assert | pass | delete | global | nonlocal`
            - `module_path`: file path (for re-indexing)
        - **ControlFlow nodes:** For `if/elif/else`, `for`, `while`, `try/except/finally`, `with`, create a `ControlFlow` node with properties:
            - `kind`: `if | for | while | try | with`
            - `condition_text`: the condition/iterator expression (e.g., `"user.is_admin"`, `"item in items"`)
            - `seq`: position among siblings in the parent body
            - `source_text`: full source of the control flow block
            - `start_line`, `end_line`
        - **Branch nodes:** Each branch within a `ControlFlow` (e.g., `if`, `elif`, `else`, `except ValueError`, `finally`) gets a `Branch` node with properties:
            - `kind`: `if | elif | else | except | finally`
            - `condition_text`: the branch condition (null for `else`/`finally`)
            - `seq`: branch order (0 for `if`, 1 for `elif`, etc.)
        - **Edges:**
            - `CONTAINS` from `Function` → `Statement`/`ControlFlow` (top-level body)
            - `CONTAINS` from `ControlFlow` → `Branch`
            - `CONTAINS` from `Branch` → `Statement`/`ControlFlow` (nested)
            - `NEXT` from `Statement` → `Statement` (sequential execution within the same parent)
            - `NEXT` from `ControlFlow` → next sibling `Statement`/`ControlFlow` (flow continues after the block)
    - **Acceptance Criteria:**
        - Given a function with an `if/else`, a `for` loop, and 5 plain statements, the graph contains the correct `Statement`, `ControlFlow`, and `Branch` nodes with accurate `CONTAINS` and `NEXT` edges.
        - Nested control flow (e.g., `if` inside `for`) produces nested `CONTAINS` relationships.
        - Traversing the `NEXT` chain from the first statement reconstructs the sequential execution order of the function body (at each nesting level).
        - Re-indexing a file correctly replaces all `Statement`/`ControlFlow`/`Branch` nodes for that file.

---

## Epic 2: Variable Mutation Tracking

- [ ] **TICKET-201: Variable & Assignment Node Extraction** *(amended)*
    - **Goal:** Promote variables to first-class graph nodes and record every assignment site with execution ordering.
    - **Tasks:**
        - Extend the tree-sitter walker to detect assignment targets: `=`, `:=`, `+=`, `-=`, `for` loop variables, `with` context variables, tuple/list unpacking.
        - Create `Variable` nodes with properties: `name`, `scope` (function-qualified, e.g., `module.Class.method.var_name`), `origin_line`, `origin_func`, `type_hint` (if annotated).
        - Create `ASSIGNS` edges from the enclosing `Function` node to the `Variable` node, with properties: `line`, `col`, `seq` (statement position within the function body), `is_rebind` (true if the variable already exists in scope), `control_context` (the `ControlFlow` condition if inside a branch, null otherwise), `branch` (which branch: `"if"`, `"else"`, `"elif 2"`, null for unconditional).
        - Handle `self.x` attribute assignments: create a `Variable` node scoped to the class, with an `ASSIGNS` edge from the method that sets it.
        - **Link to Statement nodes:** Create `PART_OF` edge from the `ASSIGNS` edge's source Statement node to the Variable, connecting the variable interaction to its statement in the flow.
    - **Acceptance Criteria:**
        - For a test file with 10 assignments (including unpacking and augmented assigns), all 10 `Variable` nodes and `ASSIGNS` edges are present in the graph.
        - `self.x` set in `__init__` and re-assigned in `update()` produces one `Variable` node with two `ASSIGNS` edges.
        - All `ASSIGNS` edges have correct `seq` values that match their position in the function body.
        - Conditional assignments carry `control_context` and `branch` properties (e.g., `control_context: "user.is_admin"`, `branch: "if"`).

- [ ] **TICKET-202: Mutation & Read Detection** *(amended)*
    - **Goal:** Distinguish in-place mutations from reads, record both as edges with execution ordering and control flow context.
    - **Tasks:**
        - Detect **mutation patterns**: method calls that mutate (`list.append`, `dict.update`, `set.add`, etc. — use a configurable allowlist), subscript assignment (`x[key] = ...`), attribute assignment on a variable (`x.attr = ...`).
        - Create `MUTATES` edges from the enclosing `Function` to the `Variable`, with properties: `line`, `seq`, `mutation_kind` (`method_call | subscript_assign | attr_assign`), `control_context`, `branch`.
        - Detect **read patterns**: any name reference that is not an assignment target or mutation call. Create `READS` edges with properties: `line`, `seq`, `control_context`, `branch`.
        - Implement a `RETURNS` edge from `Function` → `Variable` when a variable appears in a `return` or `yield` statement, with properties: `line`, `seq`, `control_context`, `branch`.
    - **Acceptance Criteria:**
        - `items.append(x)` creates a `MUTATES` edge to `items`, not an `ASSIGNS` edge.
        - `print(items)` creates a `READS` edge to `items`.
        - `return items` creates a `RETURNS` edge from the function to `items`.
        - A mutation inside an `if` block carries `control_context: "len(items) > 0"`, `branch: "if"`.
        - All edges within a function can be sorted by `seq` to reconstruct execution order.

- [ ] **TICKET-203: Cross-Function Variable Passing (`PASSES_TO`)** *(amended)*
    - **Goal:** Track a variable's identity as it crosses function call boundaries via arguments, with ordering.
    - **Tasks:**
        - When a `CALLS` edge exists from `func_a` to `func_b`, and argument position `i` in the call maps to parameter `param_i` in `func_b`'s signature, create a `PASSES_TO` edge from `func_a`'s `Variable` node to `func_b`'s `Variable` (parameter) node.
        - Handle keyword arguments by matching on parameter name.
        - Handle `*args` / `**kwargs` pass-through: if `func_b` forwards `kwargs` to `func_c`, propagate the `PASSES_TO` chain.
        - Store edge properties: `call_line`, `seq`, `arg_position`, `arg_keyword`.
    - **Acceptance Criteria:**
        - Given `def a(): x = 1; b(x)` and `def b(y): c(y)` and `def c(z): print(z)`, querying the mutation timeline of variable `x` in `a` returns the full chain: `a.x → b.y → c.z`.
        - Keyword argument passing (`b(value=x)`) correctly resolves to the right parameter node.

- [ ] **TICKET-204: Mutation Timeline Query** *(amended)*
    - **Goal:** Implement the flagship Cypher query that returns a variable's full lifecycle, including statement-level context.
    - **Tasks:**
        - Write a parameterized Cypher query that, given a `Variable` node ID (or `name` + `scope`), traverses `ASSIGNS`, `MUTATES`, `READS`, `PASSES_TO`, `RETURNS`, and `FEEDS` edges to collect every function, variable, and statement node that participates in the variable's lifecycle.
        - Return results as an ordered JSON structure: `{ origin: {...}, mutations: [...], reads: [...], passes: [...], feeds: [...], terminal: {...} }`, sorted by `seq` within each function and by file path across functions.
        - Include `control_context` and `branch` in the response so the frontend can render conditional branches.
        - Expose as a FastAPI endpoint: `GET /api/v1/variables/{variable_id}/timeline`.
    - **Acceptance Criteria:**
        - For a variable that is assigned in file A, mutated in file B (via `PASSES_TO`), and read in file C, the endpoint returns all three sites with correct file paths, line numbers, and `seq` values.
        - Conditional mutations include their `control_context` and `branch`.
        - Query executes in < 100 ms on a graph with 50k+ nodes.

- [ ] **TICKET-205: Intra-Function Data Flow (`FEEDS`)** *(new)*
    - **Goal:** Track when a read of one variable feeds into the assignment or mutation of another within the same function, completing the intra-function data flow graph.
    - **Tasks:**
        - For each assignment statement (`x = expr`), identify all variables read in `expr`. Create `FEEDS` edges from each read variable's `Variable` node to the assigned variable's `Variable` node.
        - For each mutation statement (`x.append(y)`), identify all variables read in the arguments. Create `FEEDS` edges from each read variable to the mutated variable.
        - For each `CALLS` statement (`result = foo(a, b)`), create `FEEDS` edges from argument variables to the result variable (if the return is assigned).
        - Store edge properties: `line`, `seq`, `expression_text` (the full RHS or argument expression), `via` (`assignment | mutation_arg | call_arg | call_return`).
    - **Acceptance Criteria:**
        - Given `x = a + b; y = transform(x); return y`:
            - `FEEDS` edges exist: `a → x`, `b → x`, `x → y` (via call_return).
        - Given `items.append(new_item)`:
            - `FEEDS` edge exists: `new_item → items` (via mutation_arg).
        - The full data flow within a function can be reconstructed by traversing `FEEDS` edges in `seq` order.
        - No `FEEDS` edge is created for reads that don't contribute to another variable (e.g., `print(x)` — this is a terminal read, not a feed).

---

## Epic 3: Code Generation (Graph → Code)

- [ ] **TICKET-206: Code Generator — Graph to Python** *(new)*
    - **Goal:** Reconstruct valid Python source files from the graph, enabling the round-trip: Code → Graph → [edit] → Code.
    - **Tasks:**
        - **Function body reconstruction:** Given a `Function` node, traverse its `CONTAINS` → `Statement`/`ControlFlow` subgraph. Emit `source_text` for each `Statement` in `seq` order, applying indentation based on nesting depth (each `Branch` adds one indent level).
        - **ControlFlow reconstruction:** For `ControlFlow` nodes, emit the keyword + condition (`if condition:`, `for x in items:`, `while cond:`, `try:`, `with ctx as x:`). Then recurse into each `Branch` in `seq` order, emitting the branch keyword + condition (`elif cond:`, `else:`, `except Error:`, `finally:`) and its body statements.
        - **Module reconstruction:** Given a `Module` node, emit all import statements (from `IMPORTS` edges), then all class and function definitions (from `DEFINES` edges) in their original `start_line` order.
        - **Formatting:** Apply Black-compatible formatting (4-space indent, 120-char line length). Preserve the original `source_text` as-is when no graph edits have been made to that node — only regenerate modified subtrees.
        - **Validation:** After generation, parse the output with tree-sitter to confirm it is syntactically valid Python. If not, return an error with the invalid region highlighted.
        - Expose as a FastAPI endpoint: `POST /api/v1/codegen/{module_id}` → returns `{ source: string, valid: bool, errors: [...] }`.
        - Also expose: `POST /api/v1/codegen/function/{function_id}` → returns just that function's reconstructed source.
    - **Acceptance Criteria:**
        - A module with 3 classes and 10 functions round-trips through Code → Graph → Code and produces syntactically valid Python.
        - Modified `Statement` `source_text` values in the graph produce the expected code changes in output.
        - ControlFlow nesting (if inside for inside try) produces correct indentation.
        - Unmodified functions preserve their original formatting exactly (no gratuitous reformatting).

- [ ] **TICKET-207: Round-Trip Integrity Tests** *(new)*
    - **Goal:** Prove that the Code → Graph → Code pipeline is lossless for supported Python constructs.
    - **Tasks:**
        - Build a test corpus of 20+ Python files covering: simple functions, classes with methods, nested control flow (3+ levels), decorators, type hints, docstrings, comprehensions, lambda expressions, `*args`/`**kwargs`, walrus operator (`:=`), match/case (Python 3.10+), multiline strings, f-strings, tuple unpacking.
        - For each file: parse → graph → generate → parse again → compare ASTs. The structural AST should be identical.
        - Identify and document **lossy constructs** — things the graph intentionally does not preserve (e.g., comment placement, blank line count between functions). These are acceptable losses. Semantic changes are not.
        - Implement a CI job that runs the round-trip suite on every backend change.
    - **Acceptance Criteria:**
        - 100% of test files pass the round-trip AST comparison.
        - Lossy constructs are documented in `docs/codegen-limitations.md` with rationale.
        - The round-trip test suite runs in < 10 seconds.

---

## Epic 4: The Visual Logic Layer

- [ ] **TICKET-301: Global Force-Directed Canvas** *(amended)*
    - **Goal:** Render the full repository graph with interactive exploration.
    - **Tasks:**
        - Build the React Flow entry point with a custom D3-force layout engine.
        - Implement node types with distinct visual treatments: `ModuleNode` (folder icon, muted), `ClassNode` (blue outline), `FunctionNode` (green fill), `VariableNode` (orange diamond, smaller).
        - Implement **Semantic Zoom**: at low zoom show folder clusters; at mid zoom show file nodes; at high zoom expand to function and variable nodes. Use `reactflow`'s `onViewportChange` to drive level-of-detail.
        - Edge styling: structural edges (`CALLS`, `INHERITS`) as solid lines; data-flow edges (`ASSIGNS`, `MUTATES`, `PASSES_TO`) as dashed lines with directional arrows. Color-code mutation edges in red/orange. Numbered labels on `CALLS` edges showing `call_order`.
        - Performance: virtualize off-screen nodes; target 60 fps with 2000+ visible nodes.
    - **Acceptance Criteria:**
        - A 500-file repo renders in < 2 seconds. Zoom transitions are smooth.
        - Toggling "Show Variables" layer on/off is instant.
        - `CALLS` edges display their execution order numbers.

- [ ] **TICKET-302: The "Logic Pack" Visualizer — Function Flow View** *(amended)*
    - **Goal:** Render a focused subgraph for a specific query result, including a full execution flow view for individual functions.
    - **Tasks:**
        - Create a `<LogicPackPanel>` React component that accepts an Atomic Subgraph JSON payload.
        - Implement a horizontal **timeline layout** for mutation queries: nodes arranged left-to-right in lifecycle order, with edges showing the data flow.
        - Implement a **radial layout** for call-graph queries: target function at center, callers in the first ring, transitive callers in the second ring.
        - **Function Flow View (new):** When a single function is selected, render its internal logic as a top-to-bottom flow:
            - `Statement` nodes as compact code blocks (monospace, showing `source_text`)
            - `ControlFlow` nodes as branching diamonds with condition text
            - `Branch` nodes as swim lanes diverging from the diamond
            - `NEXT` edges as vertical flow arrows
            - `Variable` nodes as labeled pills on the sides, with `ASSIGNS`/`MUTATES`/`READS` edges connecting to the statements that interact with them
            - `FEEDS` edges as horizontal arcs connecting variable pills, showing data flow
            - `CALLS` edges highlighted with numbered badges and arrow to the called function
            - Color coding: green for assignments, red for mutations, blue for reads, amber for passes
        - Highlight the "hot path" (the specific execution/mutation path the user queried) with animated edge pulses.
        - Support click-to-navigate: clicking any node in the Logic Pack fires an event that the Monaco integration consumes.
    - **Acceptance Criteria:**
        - A mutation timeline for a variable that passes through 5 functions renders as a clear left-to-right flow with labeled edges.
        - The Function Flow View for a function with an `if/else` and a `for` loop renders as a clear branching flow diagram.
        - Variables appear alongside the statements that use them, with color-coded edges.
        - Clicking a node in the Logic Pack scrolls Monaco to the correct line.

- [ ] **TICKET-303: Execution Flow Explorer** *(new)*
    - **Goal:** Enable PyCharm-like "command-click" drill-down through the call graph, showing execution flow at each level.
    - **Tasks:**
        - **Click to enter:** Clicking a `FunctionNode` on the global canvas (or in a Logic Pack) opens the Function Flow View (TICKET-302) for that function.
        - **Drill down:** Within the Function Flow View, clicking a `CALLS` edge or a called function's name opens the Function Flow View for the *called* function. A breadcrumb trail builds: `main → process_data → validate_input`.
        - **Breadcrumb navigation:** Clicking any breadcrumb item returns to that function's flow view. Back button steps up one level.
        - **Call context sidebar:** When drilled into a called function, the sidebar shows: which arguments were passed (from `PASSES_TO` edges), which variables the caller's result is assigned to, and the `call_order` position in the parent.
        - **Multi-hop variable tracking:** When a variable is selected in a parent function and you drill into a called function, the variable's identity is highlighted through the `PASSES_TO` chain — the parameter it maps to is pre-highlighted in the child's flow.
        - **Keyboard shortcuts:** `Ctrl+Click` / `Cmd+Click` on a call to drill in. `Escape` or `Backspace` to drill out.
    - **Acceptance Criteria:**
        - Starting from `main()`, drilling through 4 levels of calls builds a 4-item breadcrumb. Each level shows the correct Function Flow View.
        - Variable identity is preserved across drill-downs: selecting `x` in `main()`, drilling into `process(x)`, highlights parameter `data` in `process()` if `PASSES_TO` connects them.
        - `Escape` returns to the parent function's flow view with the call site highlighted.

---

## Epic 5: The Integrated Workspace

- [ ] **TICKET-401: Monaco Context Manager**
    - **Goal:** Integrate a full-featured code editor that stays in sync with the graph.
    - **Tasks:**
        - Integrate `@monaco-editor/react` with TypeScript language support.
        - Implement a `ModelManager` service that loads all repo files as Monaco `ITextModel` instances, keyed by file path. Lazy-load file contents on first open.
        - **Graph → Editor navigation:** When a graph node is clicked, call `editor.revealLineInCenter(node.start_line)` and set the cursor. If the node is in a different file, switch the active model first.
        - **Variable node navigation:** Clicking a `Variable` node or a mutation edge navigates to the specific `line` property of that edge/node.
        - Implement a tab bar showing open files, with a "pinned" indicator for files referenced by the current Logic Pack.
    - **Acceptance Criteria:**
        - Clicking a `FunctionNode` in the graph opens the correct file and scrolls to the function. Latency < 100 ms.
        - Clicking a `MUTATES` edge on variable `x` in `process_data()` navigates to the exact line of the mutation.

- [ ] **TICKET-402: Bidirectional Highlighting & Mutation Gutter** *(amended)*
    - **Goal:** Make the editor and graph reflect each other's state in real time, at statement-level granularity.
    - **Tasks:**
        - **Cursor → Graph:** Use Monaco's `onDidChangeCursorPosition` to determine which `Function` and `Statement` the cursor is in (binary search on `start_line`/`end_line` ranges). Dispatch a `highlightNode` event to React Flow, highlighting both the function and the specific statement in the Function Flow View.
        - **Mutation Gutter Icons:** Query all `ASSIGNS`, `MUTATES`, `READS`, and `FEEDS` edges for the active file. Render gutter decorations: green for assignment, red for mutation, blue for read, amber for feeds. Clicking a gutter icon opens the mutation timeline for that variable in the Logic Pack panel.
        - **Delta Decorations:** Highlight the line ranges of all functions referenced in the current Logic Pack with a subtle background color.
        - **Statement highlight:** When a `Statement` node is selected in the Function Flow View, highlight the corresponding line range in Monaco with a brighter background.
    - **Acceptance Criteria:**
        - Moving the cursor between functions causes the corresponding graph node to glow within 50 ms.
        - Moving the cursor between statements causes the corresponding `Statement` node in the Function Flow View to highlight.
        - Gutter icons appear for all variable interactions in the active file. Clicking a mutation icon opens the correct timeline.

- [ ] **TICKET-403: Graph-Based Code Editing** *(new)*
    - **Goal:** Allow developers to edit code by manipulating the graph, with changes written back to source files.
    - **Tasks:**
        - **Statement editing:** Double-click a `Statement` node in the Function Flow View to edit its `source_text` inline. On save, update the graph node and trigger the code generator (TICKET-206) to rewrite the containing function.
        - **Statement reordering:** Drag-and-drop `Statement` nodes to reorder them within a function body or branch. Updates `seq` values and `NEXT` edges. Triggers code regeneration.
        - **Statement insertion:** A "+" button between statements in the flow view opens an inline editor to add a new statement. Creates a new `Statement` node with the correct `seq` and adjusts surrounding `seq` values.
        - **Statement deletion:** Right-click → Delete on a `Statement` node removes it from the graph and adjusts `seq`/`NEXT` edges. Triggers code regeneration.
        - **ControlFlow manipulation:** Add new `if/for/while` blocks from a context menu. Move statements into/out of branches by dragging.
        - **Function extraction:** Select multiple `Statement` nodes → "Extract Function" creates a new `Function` node, moves the statements into it, replaces the original statements with a `CALLS` edge, and generates the function signature from the `FEEDS`/`READS` edges (variables read become parameters, variables assigned become return values).
        - **Write-back pipeline:** After any graph edit: (1) update graph nodes/edges, (2) run code generator for the affected function, (3) validate with tree-sitter, (4) if valid, write to disk, (5) emit `graph:updated` WebSocket event. If invalid, show error and revert graph edit.
        - **Monaco sync:** After write-back, update the Monaco model for the affected file. The editor reflects the change immediately.
    - **Acceptance Criteria:**
        - Editing a statement's `source_text` in the flow view produces the correct change in the source file.
        - Dragging a statement from position 3 to position 1 correctly reorders the code in the file.
        - Inserting a new statement between two existing ones produces valid Python with correct indentation.
        - "Extract Function" correctly identifies parameters and return values from the data flow graph.
        - Invalid edits (syntax errors) are caught before write-back and display a clear error.

---

## Epic 6: Atomic GraphRAG & Agent Logic

- [ ] **TICKET-501: Atomic Retrieval Query Templates**
    - **Goal:** Build a library of parameterized Cypher queries that power Logic Packs.
    - **Tasks:**
        - **Call-chain query:** Given a function ID and hop depth, return the function, its callers, its callees, and all connecting edges (ordered by `call_order`).
        - **Mutation timeline query:** (From TICKET-204) Package the result as a Logic Pack JSON with embedded source snippets for each node.
        - **Impact query:** Given a function ID, return all variables it `MUTATES` and every downstream `READS` consumer of those variables — answering *"if I change this function, what breaks?"*
        - **Class hierarchy query:** Given a class, return its full inheritance tree and all overridden methods.
        - **Function flow query (new):** Given a function ID, return its full `Statement`/`ControlFlow`/`Branch` subgraph with all `Variable` interactions — the complete data needed for the Function Flow View.
        - Each query returns a standardized `LogicPack` JSON: `{ nodes: [...], edges: [...], snippets: { node_id: "source_code" } }`.
    - **Acceptance Criteria:**
        - All five query types return valid `LogicPack` JSON.
        - The impact query correctly identifies a downstream reader 3 hops away via `PASSES_TO` chains.
        - The function flow query returns statements in `seq` order with correct nesting.

- [ ] **TICKET-502: Natural Language to Cypher Agent**
    - **Goal:** Let developers ask questions in plain English and get graph-powered answers.
    - **Tasks:**
        - Build a prompt template that includes the graph schema (node labels, edge types, key properties) and 5-10 few-shot Cypher examples.
        - Target questions: *"Where is the user object modified?"*, *"What functions call `save_order` and what do they pass to it?"*, *"Show me every mutation of `self.config` across the codebase."*, *"What's the execution flow of `process_order`?"*
        - Route the generated Cypher through the FastAPI query endpoint; feed the resulting Logic Pack into the visualizer.
        - Implement a confidence check: if the LLM's Cypher query returns zero results, retry with a relaxed query (e.g., fuzzy name match).
    - **Acceptance Criteria:**
        - The question *"What happens to the `request` variable in `handle_upload`?"* produces a Cypher query that returns the correct mutation timeline.
        - 8 out of 10 test questions produce valid, non-empty Cypher results on a sample repo.

---

## Epic 7: Live Sync & Agent Ghosting

- [ ] **TICKET-601: File System Watcher** *(amended)*
    - **Goal:** Keep the graph in sync with the codebase in real time, including statement-level nodes.
    - **Tasks:**
        - Implement a Python `watchdog` observer that watches `WATCH_PATH` for `.py` file changes (create, modify, delete).
        - On change: compute the file's new checksum. If it differs from the `Module` node's stored checksum, trigger the full parser pipeline: TICKET-102/103 (structural), TICKET-104 (statements/control flow), TICKET-201/202/203 (variables), TICKET-205 (FEEDS).
        - Emit a WebSocket event (`graph:updated { affected_modules: [...] }`) to the frontend.
        - Frontend receives the event and re-fetches visible nodes from the graph API, animating a "pulse" ripple on updated nodes. If a Function Flow View is open for an affected function, refresh it.
        - Debounce rapid saves (e.g., 300 ms) to avoid redundant re-indexes.
        - **External edit detection:** If a file is modified externally (not via TICKET-403's write-back), detect the conflict and update the graph from the file (file wins over graph for external edits).
    - **Acceptance Criteria:**
        - Saving a file in any editor triggers a visible graph pulse within 1 second.
        - Adding a new mutation to a variable (e.g., `items.append(new)`) causes a new `MUTATES` edge to appear in the graph without a full re-index.
        - An open Function Flow View updates when the underlying file changes.

- [ ] **TICKET-602: Agent "Ghost" Preview** *(amended)*
    - **Goal:** Visualize AI-proposed code changes on the graph *before* they are committed, using the Function Flow View.
    - **Tasks:**
        - Accept a proposed diff (unified diff format) from an agent. Parse it into a set of affected files and line ranges.
        - Run the full parser pipeline on the *proposed* file contents (apply the diff in memory). Produce a "shadow" set of nodes and edges.
        - Diff the shadow graph against the current graph. Categorize changes: `added_nodes`, `removed_nodes`, `added_edges`, `removed_edges`, `modified_properties`.
        - **Global canvas ghosts:** Render ghost nodes as dashed outlines and ghost edges as dashed lines. Use red for removals, green for additions.
        - **Function Flow View ghosts:** In the Function Flow View, show added `Statement` nodes with a green left border, removed statements with a red strikethrough, modified statements with a yellow highlight and an inline diff.
        - **Mutation impact:** If the proposed diff introduces a new `MUTATES` edge on a variable, highlight all downstream `READS` consumers with a warning icon — these are the functions the agent's change may affect.
        - Show a side-by-side Monaco diff view (`monaco.editor.createDiffEditor`) for the affected file.
        - Accepting the ghost applies the diff to disk and triggers the watcher (TICKET-601) for real indexing.
    - **Acceptance Criteria:**
        - A proposed change that adds a new function call renders a green dashed `CALLS` edge and a new ghost `FunctionNode`.
        - A proposed change that adds `items.sort()` shows a new `MUTATES` edge to `items` and flags all downstream readers with a warning.
        - The Function Flow View shows added/removed/modified statements with clear visual differentiation.
        - Accepting the ghost applies the diff to disk and triggers the watcher (TICKET-601) for real indexing.

---

## Execution Order

```
TICKET-101 (scaffold)
    └── TICKET-102 (structural nodes)
        └── TICKET-103 (relationship edges + ordering)
            └── TICKET-104 (statement & control flow nodes)  ← NEW
                └── TICKET-201 (variable nodes)
                    └── TICKET-202 (mutation/read edges)
                        └── TICKET-203 (PASSES_TO)
                            └── TICKET-205 (FEEDS edges)  ← NEW
                                └── TICKET-204 (mutation timeline query)
                                    ├── TICKET-206 (code generator)  ← NEW
                                    │   └── TICKET-207 (round-trip tests)  ← NEW
                                    ├── TICKET-501 (query template library)
                                    │   └── TICKET-502 (NL → Cypher agent)
                                    ├── TICKET-301 (graph canvas)
                                    │   └── TICKET-302 (Logic Pack + Function Flow View)
                                    │       └── TICKET-303 (Execution Flow Explorer)  ← NEW
                                    │           └── TICKET-401 (Monaco context manager)
                                    │               └── TICKET-402 (bidirectional highlighting)
                                    │                   └── TICKET-403 (graph-based editing)  ← NEW
                                    └── TICKET-601 (file watcher)
                                        └── TICKET-602 (ghost preview)
```

**Phase 1 (backend core):** 101 → 102 → 103 → 104 → 201 → 202 → 203 → 205 → 204

**Phase 2 (code generation):** 206 → 207

**Phase 3 (frontend + graph viz):** 301 → 302 → 303 → 401 → 402 → 403

**Phase 4 (AI layer):** 501 → 502

**Phase 5 (live sync):** 601 → 602

Phases 2, 3, 4 can begin in parallel once Phase 1 is complete. Phase 5 depends on Phases 2 and 3.
