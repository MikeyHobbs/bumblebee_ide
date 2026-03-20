# Experiment Design: Graph-Augmented Code Execution vs Standard RAG

## Thesis

Given a natural language question that requires **understanding and executing existing code**
from a codebase, an agent with graph-retrieved context (Logic Packs) answers more correctly,
in fewer steps, and with less token waste than an agent using standard file-based retrieval.

The model is not generating new code — it is **navigating an existing codebase to find,
compose, and execute the right functions to answer a question**.

## Why Graph Retrieval Should Win

Standard coding agents (Copilot, Cursor, aider) retrieve **files and chunks** — flat text.
When asked a question that requires running code, they must:

1. Search for relevant files (embedding similarity or grep)
2. Read through files hoping to find the right function
3. Figure out how to call it (what params, what imports, what setup)
4. Discover that it depends on other functions, search again
5. Chain calls together, often getting signatures wrong
6. Execute, hit errors, retry

They waste tokens reading irrelevant code, miss helper functions in other files,
call things with wrong arguments, and often give up or hallucinate.

**With a graph**, the agent already knows:
- **Which function does what** — semantic_intent, name, signature
- **How to call it** — params, return_type, TypeShapes (ACCEPTS/PRODUCES)
- **What it depends on** — CALLS edges, transitive closure via Logic Pack
- **What types flow through it** — Variable edges, TypeShape compatibility
- **The minimal source needed to execute** — snippets dict in the Logic Pack

A Logic Pack is a **pre-computed program map**. The model doesn't explore — it navigates.

## Experimental Conditions

### Condition A: No Retrieval (Control)

1. Provide the model with: question + execution sandbox only
2. Single-shot: model writes code from the question alone, no context
3. Establishes the floor — how well does the model do with no help?

### Condition B: File RAG (Controlled Baseline)

1. Chunk all source files in the repository
2. On each question, retrieve top-k most similar chunks via keyword matching
3. Provide the model with: question + retrieved chunks + execution sandbox
4. Single-shot: model reads chunks, writes execution code, gets scored

This is the controlled comparison — same model, same sandbox, isolated variable.

### Condition C: Graph RAG (Bumblebee)

1. Import the test repository into the Bumblebee graph
2. On each question, use NL-to-Cypher to find the focal node(s)
3. Build a Logic Pack for the focal node (call chain + variable flow + types)
4. Provide the model with: question + serialized Logic Pack + execution sandbox
5. Single-shot: model reads the pack, writes execution code, gets scored

Same model, same sandbox, same questions. Only the retrieval differs.

### Condition D: Agent (Ecological Baseline)

1. The model gets the question + tools (list_files, read_file, search, execute_code)
2. Multi-turn tool-use loop: model explores the repo, reads code, executes, iterates
3. Up to 10 rounds of tool calls before forced termination
4. Model calls submit_answer when it has the result

This represents what real coding agents (Cursor, aider, Claude Code) actually do.
It's the practical comparison — does pre-computed graph context beat iterative
exploration? The agent condition uses more tokens and steps, but has full autonomy.

**Why both B and D?**
- B (File RAG) isolates the retrieval variable scientifically (same model, one shot)
- D (Agent) answers the practical question ("does this beat what people actually use?")
- A reviewer needs both: the controlled experiment AND the real-world comparison

## Task Design

Each task is a natural language question about a specific codebase that requires
executing existing code to produce the answer.

### Task Categories

| Tier | Description | Example | Graph Advantage |
|------|-------------|---------|-----------------|
| **direct** | Call one known function | "What does `parse_config('test.yaml')` return?" | Minimal — both find it |
| **composition** | Chain 2-3 functions | "Run the validation pipeline on this input" | Graph knows the call chain |
| **cross-module** | Answer spans multiple files | "What happens when auth fails during import?" | Graph traverses CALLS across modules |
| **data-flow** | Track variable transformations | "What's the final state of `user` after `process_signup`?" | Graph has MUTATES/READS/PASSES_TO |
| **discovery** | Find the right function first | "How do I check if a user has admin access?" | Graph has semantic_intent + type matching |

### Task Format

```json
{
  "id": "task-001",
  "question": "What does parse_file return when given an empty Python file?",
  "category": "direct",
  "difficulty": "easy",
  "target_repo": "sample_app",
  "gold_answer": {"result": {"functions": [], "classes": [], "imports": []}},
  "gold_path": ["parsing.ast_parser.parse_file"],
  "setup_code": "# any imports or fixtures needed",
  "validation": "exact_match"
}
```

### Gold Answer Types

- **exact_match** — output must equal gold_answer exactly
- **contains** — output must contain all keys/values from gold_answer
- **type_match** — output must have the same structure/types as gold_answer
- **human_rated** — requires manual scoring (for open-ended questions)

## Metrics

### Primary Metrics

| Metric | Definition | Measurement |
|--------|-----------|-------------|
| **Answer correctness** | Does the final answer match the gold answer? | Automated comparison per validation type |
| **Execution success** | Did the code run without errors? | Binary: did the sandbox return a result? |
| **Steps to answer** | How many retrieve→reason→execute rounds? | Count tool calls / execution attempts |

### Secondary Metrics

| Metric | Definition | Measurement |
|--------|-----------|-------------|
| **Tokens consumed** | Total input + output tokens across all rounds | Sum from model API response |
| **Retrieval precision** | Did the agent find the right function(s)? | Compare executed functions to gold_path |
| **Latency** | Wall clock time from question to final answer | time.perf_counter() |
| **Error recovery** | When first attempt fails, does the agent self-correct? | Count retries that succeed |

### The Story These Metrics Tell

- **Same correctness on easy tasks** — proves the conditions are fair
- **Graph RAG wins on multi-step tasks** — the structural context matters
- **Fewer steps + fewer tokens** — the graph context is more efficient than file search
- **Higher retrieval precision** — graph finds the right functions directly

## Statistical Analysis

- **McNemar's test** for binary metrics (correct/incorrect) — paired per-task comparison
- **Wilcoxon signed-rank** for continuous metrics (steps, tokens, latency)
- **Bootstrap confidence intervals** (1000 resamples) for all metrics
- Minimum **50 tasks** in test set for statistical power
- Stratify results by category — the breakdown by difficulty tier is the key chart

## Reference Codebases

### Primary: sample_app (test_repos/sample_app/)

Already in the repository. Covers:
- Auth flow (auth/)
- HTTP handlers (handlers/)
- Data models (models/)
- Service layer with event bus (services/)
- Utility functions (utils/)

### Secondary: Bumblebee itself (self-referential)

Import Bumblebee's own backend into the graph. Questions like:
- "What model adapter does the chat endpoint use?"
- "What happens when a file change is detected by the watcher?"

This is powerful because we know the answers intimately.

## Execution Environment

Both conditions get identical sandboxes:
- Python subprocess with the test repo on sys.path
- 30-second timeout per execution
- Stdout/stderr capture
- Import restrictions (no network, no filesystem writes outside /tmp)
- The sandbox returns: exit_code, stdout, stderr, return_value (if captured)

## Implementation Phases

1. **Sandbox** — Isolated Python executor with timeout and capture
2. **File RAG baseline** — Embedding + retrieval over source files
3. **Graph RAG serializer** — Logic Pack → compact text prompt format
4. **Task set** — 50+ tasks across all categories against sample_app
5. **Eval harness** — Run all conditions, collect metrics, output report
6. **Fine-tune** — Train Mistral on graph-context examples, re-evaluate
