# BYOM (Bring Your Own Model) Architecture

Model adapter pattern, tool interface, and system prompt construction for the LLM agent layer.

---

## 6. Bring Your Own Model (BYOM) Architecture

### 6.1 Why BYOM Fits

The manifesto states that Bumblebee's value is in the **graph and Logic Packs**, not the LLM. The model is a replaceable reasoning engine. BYOM follows directly from this principle:

- **Bumblebee owns the tools.** The graph queries, mutation timelines, impact analysis, and code retrieval are tools defined by Bumblebee's backend.
- **The model owns the reasoning.** It decides when to call which tool, how to interpret results, and how to respond to the user.
- **The user owns the model choice.** Local (Ollama, llama.cpp) or cloud (Anthropic, OpenAI, etc.) -- the interface is the same.

This does **not** negate the architecture. It strengthens it:
- The pre-processed Logic Packs mean even a small 8B model gets high-density context, so local models work well.
- The tool-use pattern means the model never needs the raw codebase -- it only sees structured subgraphs.
- Swapping models doesn't change the graph, the queries, or the UI. Only the reasoning quality changes.

### 6.2 Tool Interface

The model receives these tools via the standard tool-use / function-calling protocol:

```json
{
  "tools": [
    {
      "name": "query_graph",
      "description": "Execute a Cypher query against the codebase graph and return matching nodes/edges.",
      "parameters": {
        "cypher": "string — a valid FalkorDB Cypher query"
      }
    },
    {
      "name": "mutation_timeline",
      "description": "Return the full lifecycle of a variable: assignments, mutations, reads, and cross-function passes.",
      "parameters": {
        "variable_name": "string",
        "scope": "string (optional) — fully qualified scope to disambiguate",
        "max_hops": "integer (default 10)"
      }
    },
    {
      "name": "impact_analysis",
      "description": "Given a function, return all variables it mutates and every downstream consumer.",
      "parameters": {
        "function_name": "string",
        "scope": "string (optional)"
      }
    },
    {
      "name": "get_logic_pack",
      "description": "Retrieve a Logic Pack (code snippets + subgraph) centered on a function or class.",
      "parameters": {
        "node_name": "string",
        "node_type": "'Function' | 'Class'",
        "hops": "integer (default 2)"
      }
    },
    {
      "name": "read_file",
      "description": "Read a file or line range from the indexed repository.",
      "parameters": {
        "path": "string",
        "start_line": "integer (optional)",
        "end_line": "integer (optional)"
      }
    },
    {
      "name": "edit_file",
      "description": "Propose an edit to a file. The edit is shown as a Ghost Preview before being applied.",
      "parameters": {
        "path": "string",
        "old_text": "string",
        "new_text": "string"
      }
    }
  ]
}
```

The system prompt sent to the model includes:
1. The graph schema (node labels, edge types).
2. The tool definitions above.
3. An instruction to **always use `mutation_timeline` or `get_logic_pack` before answering questions about code behavior** -- forcing the model to ground its answers in the graph rather than hallucinating from training data.

### 6.3 Model Adapter Layer

```
User prompt
    |
    v
+-------------------+
| Bumblebee Router  |  Prepends system prompt + tool defs
+-------------------+
    |
    v
+-------------------+
| Model Adapter     |  Translates to provider-specific API
|  - OllamaAdapter  |  (Ollama /api/chat with tools)
|  - OpenAIAdapter  |  (OpenAI /chat/completions)
|  - AnthropicAdapter| (Anthropic /messages with tool_use)
+-------------------+
    |
    v
+-------------------+
| Tool Executor     |  Intercepts tool calls, runs them against
|                   |  FastAPI backend, returns results to model
+-------------------+
    |
    v
  Response streamed to terminal-chat panel
```
