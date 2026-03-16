# Styling Guide: Bumblebee IDE

## 1. Design Philosophy

**Minimal. Monospaced. Mathematical.**

Bumblebee looks like a tool built by someone who reads papers, not pitch decks. The UI should feel like a high-end terminal that happens to render graphs — not a web app pretending to be an IDE. Inspiration: the typographic precision of doubleword.ai, the information density of Bloomberg Terminal, the interactivity of Figma.

Core principles:
- **Content over chrome.** No gradients, no drop shadows, no rounded-everything. Borders are 1px solid. Backgrounds are flat.
- **Monospace is the voice.** All code, all queries, all system output use a monospace typeface. Proportional type is reserved for headings and documentation panels only.
- **Math as aesthetic.** Graph labels, edge annotations, and query syntax should feel like reading a formula. Use symbols over words where unambiguous: `->`, `|`, `::`, `=>`.
- **Dark by default.** A single dark theme. No light mode (for now). The graph canvas is the hero — it needs a dark backdrop to let node colors and edge pulses pop.

---

## 2. Color System

### 2.1 Base Palette
| Token              | Value       | Usage                                    |
|--------------------|-------------|------------------------------------------|
| `--bg-primary`     | `#0a0a0a`   | Main canvas, editor background           |
| `--bg-secondary`   | `#111111`   | Panels, sidebars, input fields           |
| `--bg-tertiary`    | `#1a1a1a`   | Hover states, active tab backgrounds     |
| `--border`         | `#222222`   | All borders, dividers                    |
| `--border-focus`   | `#444444`   | Focused input borders, active panel edge |
| `--text-primary`   | `#e0e0e0`   | Body text, code                          |
| `--text-secondary` | `#777777`   | Comments, placeholders, timestamps       |
| `--text-muted`     | `#444444`   | Disabled text, subtle labels             |

### 2.2 Semantic Colors (Graph Nodes & Edges)
| Token              | Value       | Usage                                    |
|--------------------|-------------|------------------------------------------|
| `--node-module`    | `#555555`   | Module nodes (muted, structural)         |
| `--node-class`     | `#5b8dd9`   | Class nodes (cool blue)                  |
| `--node-function`  | `#4ec990`   | Function nodes (green, primary action)   |
| `--node-variable`  | `#e8a838`   | Variable nodes (amber, attention)        |
| `--edge-structural`| `#333333`   | CALLS, INHERITS, IMPORTS (subtle)        |
| `--edge-mutation`  | `#d94444`   | MUTATES edges (red, danger)              |
| `--edge-assign`    | `#4ec990`   | ASSIGNS edges (green, creation)          |
| `--edge-pass`      | `#e8a838`   | PASSES_TO edges (amber, movement)        |
| `--edge-read`      | `#5b8dd9`   | READS edges (blue, passive)              |
| `--ghost-add`      | `#4ec99066` | Ghost preview: additions (green, 40%)    |
| `--ghost-remove`   | `#d9444466` | Ghost preview: removals (red, 40%)       |

### 2.3 Terminal / Chat Accent
| Token              | Value       | Usage                                    |
|--------------------|-------------|------------------------------------------|
| `--prompt`         | `#4ec990`   | User prompt prefix (`>`)                 |
| `--system`         | `#777777`   | System messages, tool output headers     |
| `--tool-call`      | `#e8a838`   | Tool invocation labels (`[query_graph]`) |
| `--tool-result`    | `#5b8dd9`   | Tool result blocks                       |
| `--error`          | `#d94444`   | Error messages                           |
| `--success`        | `#4ec990`   | Success confirmations                    |

---

## 3. Typography

### 3.1 Typefaces
| Role          | Font                              | Fallback                    |
|---------------|-----------------------------------|-----------------------------|
| **Mono**      | `JetBrains Mono`                  | `SF Mono`, `Consolas`, mono |
| **Sans**      | `Inter`                           | `system-ui`, sans-serif     |
| **Math/Label**| `JetBrains Mono` (italic variant) | --                          |

### 3.2 Scale
| Token       | Size     | Weight | Usage                        |
|-------------|----------|--------|------------------------------|
| `--h1`      | `1.5rem` | 600    | Panel titles (rare)          |
| `--h2`      | `1.1rem` | 600    | Section headers              |
| `--body`    | `0.875rem` | 400  | All body text, code          |
| `--small`   | `0.75rem` | 400   | Timestamps, edge labels, gutter |
| `--tiny`    | `0.625rem` | 400  | Node labels at low zoom      |

**Rule:** Never go above `1.5rem`. The UI should feel dense and information-rich, not spacious.

---

## 4. Layout: The Three-Panel Architecture

```
+-----------------------------------------------------+
|  [tabs: open files]                    [⚙] [?]      |  <- Top bar (28px, --bg-secondary)
+----------------+-------------------+-----------------+
|                |                   |                  |
|   GRAPH        |   EDITOR          |   TERMINAL /    |
|   CANVAS       |   (Monaco)        |   CHAT PANEL    |
|                |                   |                  |
|   React Flow   |   Full Monaco     |   Hybrid        |
|   force graph  |   with gutter     |   terminal +    |
|                |   mutation icons  |   AI chat       |
|                |                   |                  |
+----------------+-------------------+-----------------+
|  [status bar: graph stats, index status, model]      |  <- Bottom bar (24px, --bg-secondary)
+-----------------------------------------------------+
```

- All three panels are **resizable** via drag handles (thin 4px borders, `--border`).
- Default split: 30% graph / 40% editor / 30% terminal-chat.
- Any panel can be collapsed to 0% or maximized to 100% with a keyboard shortcut.
- The **Logic Pack Visualizer** replaces the graph panel when a query result is active (toggle back with `Esc`).

---

## 5. The Terminal-Chat Hybrid

### 5.1 Core Concept

The right panel is not a chatbot. It is not a terminal. It is **both** — a single interface where you type commands, ask questions, and see tool-use unfold in real time. Think: Claude Code's terminal UX, but with a graph-aware tool belt.

### 5.2 Interaction Model

```
┌─────────────────────────────────────────────────┐
│  bumblebee v0.1.0 | model: qwen3-8b | graph: ✓ │  <- Status header
├─────────────────────────────────────────────────┤
│                                                  │
│  > what happens to `request.body` after          │  <- User prompt (green `>`)
│    it enters `validate_payload`?                 │
│                                                  │
│  [query_graph] mutation_timeline                 │  <- Tool call (amber)
│    variable: request.body                        │
│    scope: api.routes.validate_payload            │
│    hops: 5                                       │
│                                                  │
│  ┌─ result ─────────────────────────────────┐    │  <- Tool result (blue border)
│  │ request.body                              │    │
│  │   ASSIGNS  validate_payload    :14        │    │
│  │   PASSES_TO  parse_json.data   :8         │    │
│  │   MUTATES  sanitize.data       :22  .strip│    │
│  │   PASSES_TO  save_record.payload :31      │    │
│  │   READS  db_client.insert      :45        │    │
│  └───────────────────────────────────────────┘    │
│                                                  │
│  The `request.body` variable flows through 4     │
│  functions. It is mutated once in `sanitize()`   │
│  via `.strip()` on line 22. The terminal         │
│  consumer is `db_client.insert()`.               │
│                                                  │
│  [View in graph] [Jump to sanitize:22]           │  <- Action links
│                                                  │
│  > _                                             │  <- Next prompt
│                                                  │
└─────────────────────────────────────────────────┘
```

### 5.3 Message Types & Rendering

| Type            | Prefix / Chrome                     | Font          | Color             |
|-----------------|-------------------------------------|---------------|-------------------|
| **User prompt** | `> ` prefix                         | Mono, normal  | `--text-primary`  |
| **Tool call**   | `[tool_name]` label, indented body  | Mono, normal  | `--tool-call`     |
| **Tool result** | Bordered block, `-- result --`      | Mono, normal  | `--tool-result`   |
| **AI response** | No prefix, plain text               | Mono, normal  | `--text-primary`  |
| **System**      | `::` prefix                         | Mono, italic  | `--text-secondary`|
| **Error**       | `!! ` prefix                        | Mono, bold    | `--error`         |
| **Action link** | `[label]` in brackets               | Mono, normal  | `--node-function` |

**Everything is monospace.** No bubbles. No avatars. No left/right alignment. Messages flow top-to-bottom like a terminal log.

### 5.4 Direct Commands

The terminal also accepts direct commands (no AI involved):

```
> /index ./my_project              # Trigger a full re-index
> /query MATCH (f:Function)-[:CALLS]->(g) WHERE f.name = 'main' RETURN g
> /timeline request.body           # Shortcut for mutation timeline
> /impact save_record              # Show downstream impact of a function
> /model ollama/qwen3-8b           # Switch the active model
> /model anthropic/claude-sonnet   # Switch to a cloud model
```

Commands prefixed with `/` are handled locally by Bumblebee. Everything else is routed to the active model.

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

---

## 7. Graph Canvas Styling

### 7.1 Nodes
- **Shape:** Rounded rectangles for Module/Class/Function. **Diamonds** for Variable nodes (smaller, 60% scale).
- **Border:** 1px solid, colored by type. No fill — just border + label on dark background.
- **Label:** Node name in `--body` mono, centered. Truncate with `...` at 20 chars.
- **Hover:** Border brightens to full saturation. Tooltip shows full name, file path, line range.
- **Selected:** 2px border, subtle glow (box-shadow with node color at 30% opacity).

### 7.2 Edges
- **Structural** (`CALLS`, `INHERITS`, `IMPORTS`): 1px solid `--edge-structural`. Straight or gentle curve.
- **Data-flow** (`ASSIGNS`, `MUTATES`, `READS`, `PASSES_TO`): 1px dashed, colored by type. Animated dash offset on hover/selection.
- **Direction:** Small arrowhead at target. No labels by default — show on hover or when part of an active Logic Pack.
- **Pulse animation:** When the graph updates (file save), affected edges flash once with a traveling dot animation (200ms, ease-out).

### 7.3 Ghost Preview Overlay
- Ghost nodes: Dashed border, `--ghost-add` or `--ghost-remove` fill at 10% opacity.
- Ghost edges: Dashed, same color rules, 50% opacity.
- A subtle pulsing animation on ghost elements to distinguish them from real graph state.

---

## 8. Component Styling Rules

### 8.1 Inputs
- Background: `--bg-secondary`.
- Border: 1px solid `--border`. On focus: `--border-focus`.
- Text: `--text-primary`, monospace.
- No border-radius. Sharp corners everywhere.
- Placeholder text: `--text-muted`.

### 8.2 Buttons
- **Primary:** `--bg-secondary` background, `--text-primary` text, 1px `--border` border. On hover: `--bg-tertiary`.
- **Ghost:** No background, no border. `--text-secondary` text. On hover: `--text-primary`.
- No uppercase transforms. No icons-only (always include a text label).

### 8.3 Panels & Dividers
- Panel backgrounds: `--bg-primary`.
- Panel headers: `--bg-secondary`, `--small` font, uppercase mono labels.
- Dividers: 1px solid `--border`. Drag handles: 4px wide, `--bg-secondary`, cursor `col-resize`.

### 8.4 Scrollbars
- Thin (6px), `--bg-tertiary` track, `--border-focus` thumb.
- Only visible on hover (auto-hide).

---

## 9. Animation & Motion

- **Duration:** 150ms for UI interactions (hover, focus). 300ms for panel transitions. 500ms for graph layout animations.
- **Easing:** `ease-out` for entrances, `ease-in` for exits.
- **Graph pulse:** A radial ring that expands from an updated node (200ms, opacity 1 -> 0, scale 1 -> 1.5).
- **No gratuitous animation.** If it doesn't communicate state change, it doesn't animate.

---

## 10. Responsive Behavior

Bumblebee is a **desktop-first** tool. Minimum viewport: 1280x720.

- Below 1440px: Collapse to two panels (editor + terminal-chat). Graph accessible via tab toggle.
- Below 1280px: Single panel mode with tab switching.
- No mobile support. This is a professional tool.
