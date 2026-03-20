import { useState, useRef, useEffect, useCallback } from "react";
import { Send } from "lucide-react";
import { useGraphStore } from "@/store/graphStore";
import { useEditorStore, type EditorTab } from "@/store/editorStore";
import type { GraphNode, GraphEdge } from "@/types/graph";

interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool_call" | "tool_result" | "cypher_result" | "cli_result";
  content: string;
  timestamp: number;
}

// ---------------------------------------------------------------------------
// Input mode detection
// ---------------------------------------------------------------------------

const CYPHER_KEYWORDS = /^\s*(MATCH|RETURN|CREATE|MERGE|DELETE|DETACH|SET|REMOVE|WITH|UNWIND|CALL|OPTIONAL)\b/i;
const VFS_CYPHER_PREFIX = /^\s*vfs\s+/i;
const VFS_NL_PREFIX = /^\s*vfs\s*\?\s*/i;
const NL_PREFIX = /^\s*(\?|ask\s)/i;
const CLI_COMMANDS = /^\s*(ls|cd|pwd|cat|tree|find|info|help)\b/i;

function inputMode(text: string): "cypher" | "cypher_vfs" | "nl" | "nl_vfs" | "cli" {
  const t = text.trim();
  if (VFS_NL_PREFIX.test(t)) return "nl_vfs";
  if (VFS_CYPHER_PREFIX.test(t)) return "cypher_vfs";
  if (CYPHER_KEYWORDS.test(t)) return "cypher";
  if (NL_PREFIX.test(t)) return "nl";
  if (CLI_COMMANDS.test(t)) return "cli";
  // Default: if it looks like a path or short word, treat as cli; otherwise nl
  return "cli";
}

function stripNlPrefix(text: string): string {
  return text.trim().replace(/^\?\s*/, "").replace(/^ask\s+/i, "");
}

// ---------------------------------------------------------------------------
// Cypher helpers
// ---------------------------------------------------------------------------

interface CypherNode {
  id: string;
  label: string;
  properties: Record<string, unknown>;
}

interface CypherEdge {
  type: string;
  source: string;
  target: string;
  properties: Record<string, unknown>;
}

interface CypherQueryResponse {
  nodes: CypherNode[];
  edges: CypherEdge[];
  raw_results: Array<Array<string | number | null>>;
}

function formatCypherResults(data: CypherQueryResponse): string {
  const parts: string[] = [];

  if (data.raw_results.length > 0) {
    parts.push(`${data.raw_results.length} row(s) returned`);
    for (const row of data.raw_results) {
      parts.push("  " + row.map((v) => (v === null ? "null" : String(v))).join(" | "));
    }
  }

  if (data.nodes.length > 0) {
    parts.push("");
    parts.push(`Nodes (${data.nodes.length}):`);
    for (const n of data.nodes) {
      const props = Object.entries(n.properties)
        .filter(([k]) => k !== "name")
        .map(([k, v]) => `${k}: ${String(v)}`)
        .join(", ");
      parts.push(`  (${n.label}) ${n.id}${props ? "  {" + props + "}" : ""}`);
    }
  }

  if (data.edges.length > 0) {
    parts.push("");
    parts.push(`Edges (${data.edges.length}):`);
    for (const e of data.edges) {
      const props = Object.entries(e.properties)
        .map(([k, v]) => `${k}: ${String(v)}`)
        .join(", ");
      parts.push(`  ${e.source} -[${e.type}]-> ${e.target}${props ? "  {" + props + "}" : ""}`);
    }
  }

  if (parts.length === 0) {
    return "(no results)";
  }

  return parts.join("\n");
}

// ---------------------------------------------------------------------------
// CLI command helpers
// ---------------------------------------------------------------------------

/** A node from either the raw query or subgraph endpoint. */
type AnyNode = CypherNode | GraphNode;

/** Format a single node for ls/tree output. */
function formatNodeLine(n: AnyNode, indent = ""): string {
  const line = typeof n.properties["start_line"] === "number" ? `:${n.properties["start_line"]}` : "";
  const label = n.label;
  const name = localName(n.id);
  return `${indent}[${label}] ${name}${line}`;
}

function localName(qualifiedName: string): string {
  const parts = qualifiedName.split(".");
  return parts[parts.length - 1] ?? qualifiedName;
}

interface SubgraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

function TerminalChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [isStreaming, setIsStreaming] = useState(false);
  const [history, setHistory] = useState<string[]>([]);
  const historyIndexRef = useRef(-1);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const tabCompletionsRef = useRef<string[]>([]);
  const tabIndexRef = useRef(-1);
  const tabPrefixRef = useRef("");

  // Graph store hooks for navigation sync
  const viewMode = useGraphStore((s) => s.viewMode);
  const activeNodeId = useGraphStore((s) => s.activeNodeId);
  const breadcrumb = useGraphStore((s) => s.breadcrumb);
  const navigateToNode = useGraphStore((s) => s.navigateToNode);
  const navigateBack = useGraphStore((s) => s.navigateBack);
  const goHome = useGraphStore((s) => s.goHome);
  const showQueryResult = useGraphStore((s) => s.showQueryResult);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // ---------------------------------------------------------------------------
  // Helpers to add messages
  // ---------------------------------------------------------------------------

  const addMsg = useCallback(
    (role: ChatMessage["role"], content: string) => {
      setMessages((prev) => [
        ...prev,
        { id: `${role}-${Date.now()}-${Math.random()}`, role, content, timestamp: Date.now() },
      ]);
    },
    [],
  );

  // ---------------------------------------------------------------------------
  // CLI command executor
  // ---------------------------------------------------------------------------

  const executeCli = useCallback(
    async (raw: string) => {
      const parts = raw.trim().split(/\s+/);
      const cmd = (parts[0] ?? "").toLowerCase();
      const arg = parts.slice(1).join(" ");

      if (cmd === "help") {
        addMsg("cli_result", [
          "Commands:",
          "  ls              List children of current node",
          "  cd <name>       Drill into a node (file, class, function)",
          "  cd ..           Go up one level",
          "  cd /            Return to root (modules view)",
          "  pwd             Print current breadcrumb path",
          "  cat <name>      Show source text of a node",
          "  tree            Tree view of children",
          "  find <pattern>  Search nodes by name in current scope",
          "  info <name>     Show node properties and edges",
          "  help            This message",
          "",
          "Prefixes:",
          "  MATCH ...       Cypher query (auto-detected)",
          "  vfs MATCH ...   Cypher query + project matched modules to .bumblebee/vfs/",
          "  ? <question>    Natural language query via LLM",
          "  ask <question>  Natural language query via LLM",
          "  vfs? <question> NL query via LLM + project results to .bumblebee/vfs/",
        ].join("\n"));
        return;
      }

      if (cmd === "pwd") {
        const path = breadcrumb.map((b) => b.label).join(" / ");
        addMsg("cli_result", path || "/");
        return;
      }

      if (cmd === "cd") {
        if (!arg || arg === "/") {
          goHome();
          addMsg("cli_result", "/");
          return;
        }
        if (arg === "..") {
          if (breadcrumb.length > 1) {
            navigateBack(breadcrumb.length - 2);
            const parent = breadcrumb[breadcrumb.length - 2];
            addMsg("cli_result", parent?.label ?? "/");
          } else {
            addMsg("system", "Already at root");
          }
          return;
        }
        // Search for a matching node by name
        const children = await fetchCurrentChildren();
        if (!children) {
          addMsg("system", "Cannot list children in this view");
          return;
        }
        const match = children.nodes.find((n) => {
          const name = localName(n.id);
          return name === arg || n.id === arg || name.toLowerCase() === arg.toLowerCase();
        });
        if (!match) {
          const partial = children.nodes.find((n) => {
            const name = localName(n.id).toLowerCase();
            return name.includes(arg.toLowerCase());
          });
          if (partial) {
            navigateToNode(partial.id, localName(partial.id));
            addMsg("cli_result", `→ ${localName(partial.id)}`);
          } else {
            addMsg("system", `Not found: ${arg}`);
          }
          return;
        }
        navigateToNode(match.id, localName(match.id));
        addMsg("cli_result", `→ ${localName(match.id)}`);
        return;
      }

      if (cmd === "ls") {
        const children = await fetchCurrentChildren();
        if (!children || children.nodes.length === 0) {
          addMsg("cli_result", "(empty)");
          return;
        }
        const lines = children.nodes.map((n) => formatNodeLine(n));
        addMsg("cli_result", lines.join("\n"));
        return;
      }

      if (cmd === "tree") {
        const children = await fetchCurrentChildren();
        if (!children || children.nodes.length === 0) {
          addMsg("cli_result", "(empty)");
          return;
        }
        // For tree, show children and for each Class, fetch its methods
        const lines: string[] = [];
        for (const n of children.nodes) {
          lines.push(formatNodeLine(n));
          if (n.label === "Class") {
            try {
              const classData = await fetchJson<SubgraphResponse>(
                `/api/v1/graph/class/${encodeURIComponent(n.id)}`,
              );
              if (classData) {
                for (const m of classData.nodes) {
                  if (m.label === "Function") {
                    lines.push(formatNodeLine(m, "  "));
                  }
                }
              }
            } catch { /* skip */ }
          }
        }
        addMsg("cli_result", lines.join("\n"));
        return;
      }

      if (cmd === "cat") {
        if (!arg) {
          addMsg("system", "Usage: cat <name>");
          return;
        }
        // Look up the node and show its source_text
        try {
          const res = await fetchJson<CypherQueryResponse>("/api/v1/query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              cypher: `MATCH (n) WHERE n.name CONTAINS '${arg.replace(/'/g, "\\'")}' RETURN n LIMIT 1`,
            }),
          });
          if (res && res.nodes.length > 0) {
            const node = res.nodes[0]!;
            const source = node.properties["source_text"];
            if (typeof source === "string") {
              addMsg("cli_result", source);
            } else {
              addMsg("cli_result", `(${node.label}) ${node.id} — no source_text`);
            }
          } else {
            addMsg("system", `Not found: ${arg}`);
          }
        } catch {
          addMsg("system", `Failed to fetch: ${arg}`);
        }
        return;
      }

      if (cmd === "find") {
        if (!arg) {
          addMsg("system", "Usage: find <pattern>");
          return;
        }
        try {
          const scope = activeNodeId
            ? `MATCH (scope:LogicNode {id: '${activeNodeId.replace(/'/g, "\\'")}'})-[:CALLS|DEPENDS_ON*1..4]->(n:LogicNode) WHERE n.name =~ '(?i).*${arg.replace(/'/g, "\\'")}.*' RETURN n LIMIT 20`
            : `MATCH (n:LogicNode) WHERE n.name =~ '(?i).*${arg.replace(/'/g, "\\'")}.*' RETURN n LIMIT 20`;
          const res = await fetchJson<CypherQueryResponse>("/api/v1/query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cypher: scope }),
          });
          if (res && res.nodes.length > 0) {
            const lines = res.nodes.map((n) => formatNodeLine(n));
            addMsg("cli_result", lines.join("\n"));
          } else {
            addMsg("cli_result", `No matches for: ${arg}`);
          }
        } catch {
          addMsg("system", `Search failed for: ${arg}`);
        }
        return;
      }

      if (cmd === "info") {
        if (!arg) {
          addMsg("system", "Usage: info <name>");
          return;
        }
        try {
          const res = await fetchJson<CypherQueryResponse>("/api/v1/query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              cypher: `MATCH (n) WHERE n.name CONTAINS '${arg.replace(/'/g, "\\'")}' RETURN n LIMIT 1`,
            }),
          });
          if (res && res.nodes.length > 0) {
            const node = res.nodes[0]!;
            const propLines = Object.entries(node.properties)
              .filter(([k]) => k !== "source_text")
              .map(([k, v]) => `  ${k}: ${String(v)}`);
            addMsg("cli_result", `(${node.label}) ${node.id}\n${propLines.join("\n")}`);
          } else {
            addMsg("system", `Not found: ${arg}`);
          }
        } catch {
          addMsg("system", `Failed to fetch: ${arg}`);
        }
        return;
      }

      addMsg("system", `Unknown command: ${cmd}. Type 'help' for available commands.`);
    },
    [breadcrumb, viewMode, activeNodeId, navigateBack, goHome, navigateToNode, addMsg],
  );

  /** Fetch JSON helper. */
  async function fetchJson<T>(url: string, init?: RequestInit): Promise<T | null> {
    try {
      const res = await fetch(url, init);
      if (!res.ok) return null;
      return (await res.json()) as T;
    } catch {
      return null;
    }
  }

  /** Fetch children of the current graph position. */
  async function fetchCurrentChildren(): Promise<SubgraphResponse | null> {
    if (viewMode === "knowledge-graph") {
      if (activeNodeId) {
        // Focused on a specific node — fetch its connected nodes
        const edges = await fetchJson<Array<{ type: string; source: string; target: string }>>(
          `/api/v1/nodes/${activeNodeId}/edges?direction=outgoing`,
        );
        if (!edges) return null;
        const nodeIds = edges.map((e) => e.target);
        const nodes = await Promise.all(
          nodeIds.slice(0, 20).map((id) =>
            fetchJson<{ id: string; name: string; kind: string; module_path: string }>(`/api/v1/nodes/${id}`),
          ),
        );
        return {
          nodes: nodes.filter(Boolean).map((n) => ({
            id: n!.id,
            label: "LogicNode" as const,
            properties: { name: n!.name, kind: n!.kind, module_path: n!.module_path },
          })),
          edges: [],
        };
      }
      // Overview mode — fetch all LogicNodes as a flat list
      const nodes = await fetchJson<Array<{ id: string; name: string; kind: string; module_path: string }>>("/api/v1/nodes?limit=200");
      if (!nodes) return null;
      return {
        nodes: nodes.map((n) => ({
          id: n.id,
          label: "LogicNode" as const,
          properties: { name: n.name, kind: n.kind, module_path: n.module_path },
        })),
        edges: [],
      };
    }
    return null;
  }

  // ---------------------------------------------------------------------------
  // VFS projection helper (shared by Cypher and NL executors)
  // ---------------------------------------------------------------------------

  const projectNodesToVfs = useCallback(
    async (vfsNodes: GraphNode[], label: string) => {
      const sources: string[] = [];
      const nodeIds: string[] = [];
      const modulePaths = new Set<string>();

      for (const node of vfsNodes) {
        const src = node.properties["source_text"];
        const mp = node.properties["module_path"];
        if (typeof src === "string" && src.trim()) {
          sources.push(src);
          nodeIds.push(node.id);
        }
        if (typeof mp === "string" && mp) modulePaths.add(mp);
      }

      // Open a compose tab with all matched functions assembled
      if (sources.length > 0) {
        const assembled = sources.join("\n\n");
        const tabId = crypto.randomUUID();
        const queryShort = label.length > 25 ? label.slice(0, 22) + "..." : label;
        const tab: EditorTab = {
          id: tabId,
          label: `vfs: ${queryShort}`,
          nodeId: null,
          modulePath: `__vfs_query__.${tabId}`,
          content: assembled,
          language: "python",
          sourceNodeIds: nodeIds,
          flowId: null,
          gaps: null,
          isDirty: false,
        };
        useEditorStore.getState().openTab(tab);
        addMsg("system", `VFS: opened ${sources.length} function${sources.length !== 1 ? "s" : ""} in editor`);
      }

      // Also project to disk
      if (modulePaths.size > 0) {
        try {
          const vfsRes = await fetch("/api/v1/vfs/project-modules", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ module_paths: [...modulePaths] }),
          });
          if (vfsRes.ok) {
            const report = (await vfsRes.json()) as { files_written: number; modules_projected: number; errors: string[] };
            addMsg("system", `VFS: projected ${report.modules_projected} module${report.modules_projected !== 1 ? "s" : ""} to .bumblebee/vfs/`);
          }
        } catch {
          // disk projection is secondary — don't block on failure
        }
      }
    },
    [addMsg],
  );

  // ---------------------------------------------------------------------------
  // Cypher executor
  // ---------------------------------------------------------------------------

  const executeCypher = useCallback(
    async (cypher: string, projectToVfs = false) => {
      setIsStreaming(true);
      try {
        // Run both the raw query (for text output) and subgraph query (for graph view) in parallel
        const [rawRes, subgraphRes] = await Promise.all([
          fetch("/api/v1/query", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cypher }),
          }),
          fetch("/api/v1/graph/query-subgraph", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ cypher }),
          }),
        ]);

        if (!rawRes.ok) {
          const errText = await rawRes.text().catch(() => "Unknown error");
          addMsg("system", `Query error: ${errText}`);
          return;
        }
        const data = (await rawRes.json()) as CypherQueryResponse;
        addMsg("cypher_result", formatCypherResults(data));

        // Push nodes into the graph canvas if there are any
        if (subgraphRes.ok) {
          const subgraph = (await subgraphRes.json()) as SubgraphResponse;
          if (subgraph.nodes.length > 0) {
            const label = cypher.length > 30 ? cypher.slice(0, 27) + "..." : cypher;
            showQueryResult(label, subgraph.nodes, subgraph.edges);
          }

          if (projectToVfs && subgraph.nodes.length > 0) {
            await projectNodesToVfs(subgraph.nodes, cypher);
          }
        }
      } catch (err) {
        addMsg("system", err instanceof Error ? err.message : "Query failed");
      } finally {
        setIsStreaming(false);
      }
    },
    [addMsg, showQueryResult, projectNodesToVfs],
  );

  // ---------------------------------------------------------------------------
  // Natural language (LLM) executor
  // ---------------------------------------------------------------------------

  const executeNl = useCallback(
    async (text: string, projectToVfs = false) => {
      setIsStreaming(true);
      const controller = new AbortController();
      abortRef.current = controller;

      try {
        // No history — each NL query is an independent data-fetch; sending
        // stale history (consecutive user messages with no assistant reply
        // after early abort) causes the LLM to repeat prior answers.
        const res = await fetch("/api/v1/chat", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ message: text }),
          signal: controller.signal,
        });

        if (!res.ok) {
          const errText = await res.text().catch(() => "Unknown error");
          addMsg("system", `Error: ${errText}`);
          setIsStreaming(false);
          return;
        }

        const reader = res.body?.getReader();
        if (!reader) { setIsStreaming(false); return; }

        const decoder = new TextDecoder();
        let assistantContent = "";
        const assistantId = `assistant-${Date.now()}`;

        setMessages((prev) => [
          ...prev,
          { id: assistantId, role: "assistant", content: "", timestamp: Date.now() },
        ]);

        let done = false;
        while (!done) {
          const result = await reader.read();
          done = result.done;
          if (result.value) {
            const chunk = decoder.decode(result.value, { stream: true });
            const lines = chunk.split("\n");
            for (const line of lines) {
              if (line.startsWith("data: ")) {
                const data = line.slice(6);
                if (data === "[DONE]") { done = true; break; }
                try {
                  const parsed: unknown = JSON.parse(data);
                  if (parsed !== null && typeof parsed === "object" && "type" in parsed) {
                    const tp = parsed as Record<string, unknown>;
                    const eventContent = typeof tp["content"] === "string" ? tp["content"] : "";

                    if (tp["type"] === "token") {
                      assistantContent += eventContent;
                      setMessages((prev) =>
                        prev.map((m) =>
                          m.id === assistantId ? { ...m, content: assistantContent } : m,
                        ),
                      );
                    } else if (tp["type"] === "tool_call") {
                      const toolName = typeof tp["name"] === "string" ? tp["name"] : "unknown";
                      const argsStr = tp["arguments"] ? JSON.stringify(tp["arguments"]) : "";
                      addMsg("tool_call", `${toolName}: ${argsStr}`);
                    } else if (tp["type"] === "tool_result") {
                      const toolName = typeof tp["name"] === "string" ? tp["name"] : "";
                      // Extract result content for display
                      const resultData = tp["result"];
                      const resultStr = resultData
                        ? (typeof resultData === "string" ? resultData : JSON.stringify(resultData, null, 2))
                        : eventContent;
                      addMsg("tool_result", `${toolName}: ${resultStr}`);
                      // Extract nodes/edges and highlight immediately
                      if (resultData && typeof resultData === "object") {
                        const rd = resultData as Record<string, unknown>;
                        const inner = (rd["result"] ?? rd) as Record<string, unknown>;
                        const resultNodes: GraphNode[] = [];
                        const resultEdges: GraphEdge[] = [];
                        if (Array.isArray(inner["nodes"])) {
                          for (const n of inner["nodes"] as GraphNode[]) {
                            if (n.id) resultNodes.push(n);
                          }
                        }
                        if (Array.isArray(inner["edges"])) {
                          resultEdges.push(...(inner["edges"] as GraphEdge[]));
                        }
                        if (resultNodes.length > 0) {
                          showQueryResult(text.slice(0, 30), resultNodes, resultEdges);
                          if (projectToVfs) {
                            void projectNodesToVfs(resultNodes, text);
                          }
                          // Data is captured — abort the stream so the LLM doesn't waste time summarising
                          controller.abort();
                          done = true;
                        }
                      }
                    }
                  }
                } catch { /* skip */ }
              }
            }
          }
        }
        // Remove the assistant message if it's still empty (e.g. aborted after tool_result)
        if (!assistantContent.trim()) {
          setMessages((prev) => prev.filter((m) => m.id !== assistantId));
        }
      } catch (err) {
        if (!(err instanceof DOMException && err.name === "AbortError")) {
          addMsg("system", err instanceof Error ? err.message : "Connection failed");
        }
      } finally {
        setIsStreaming(false);
        abortRef.current = null;
      }
    },
    [addMsg, showQueryResult, projectNodesToVfs],
  );

  // ---------------------------------------------------------------------------
  // Main dispatch
  // ---------------------------------------------------------------------------

  const sendMessage = useCallback(
    async (text: string) => {
      if (!text.trim() || isStreaming) return;

      // Push to command history
      setHistory((prev) => [text.trim(), ...prev.slice(0, 99)]);
      historyIndexRef.current = -1;

      const userMsg: ChatMessage = {
        id: `user-${Date.now()}`,
        role: "user",
        content: text.trim(),
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, userMsg]);
      setInput("");

      const mode = inputMode(text);
      if (mode === "nl_vfs") {
        const question = text.trim().replace(VFS_NL_PREFIX, "").trim();
        await executeNl(question, true);
      } else if (mode === "cypher_vfs") {
        const cypher = text.trim().replace(VFS_CYPHER_PREFIX, "").trim();
        await executeCypher(cypher, true);
      } else if (mode === "cypher") {
        await executeCypher(text.trim());
      } else if (mode === "nl") {
        await executeNl(stripNlPrefix(text));
      } else {
        await executeCli(text.trim());
      }
    },
    [isStreaming, executeCypher, executeNl, executeCli],
  );

  const handleSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      void sendMessage(input);
    },
    [input, sendMessage],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Tab") {
        e.preventDefault();
        void (async () => {
          // Extract the word being completed
          const parts = input.trimStart().split(/\s+/);
          const cmd = (parts[0] ?? "").toLowerCase();
          const partial = parts.length > 1 ? parts[parts.length - 1]! : "";

          // If this is a fresh Tab press (not cycling), build completion list
          if (tabPrefixRef.current !== partial || tabCompletionsRef.current.length === 0) {
            tabPrefixRef.current = partial;
            tabIndexRef.current = -1;

            // Command-level completion
            if (parts.length <= 1 && !cmd.startsWith("?") && !CYPHER_KEYWORDS.test(input)) {
              const cmds = ["ls", "cd", "pwd", "cat", "tree", "find", "info", "help"];
              tabCompletionsRef.current = cmds.filter((c) => c.startsWith(partial.toLowerCase()));
            } else if (["cd", "cat", "info", "find"].includes(cmd)) {
              // Node name completion from current scope
              const children = await fetchCurrentChildren();
              if (children) {
                const names = children.nodes.map((n) => localName(n.id));
                tabCompletionsRef.current = partial
                  ? names.filter((n) => n.toLowerCase().startsWith(partial.toLowerCase()))
                  : names;
              } else {
                tabCompletionsRef.current = [];
              }
            } else {
              tabCompletionsRef.current = [];
            }
          }

          // Cycle through completions
          if (tabCompletionsRef.current.length > 0) {
            tabIndexRef.current = (tabIndexRef.current + 1) % tabCompletionsRef.current.length;
            const completion = tabCompletionsRef.current[tabIndexRef.current]!;
            if (parts.length <= 1) {
              setInput(completion);
            } else {
              // Replace the last word with the completion
              const prefix = parts.slice(0, -1).join(" ");
              setInput(prefix + " " + completion);
            }
          }
        })();
        return;
      }

      // Any non-Tab key resets tab completion state
      tabCompletionsRef.current = [];
      tabIndexRef.current = -1;
      tabPrefixRef.current = "";

      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        void sendMessage(input);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const next = Math.min(historyIndexRef.current + 1, history.length - 1);
        if (next >= 0 && history[next]) {
          setInput(history[next]);
          historyIndexRef.current = next;
        }
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        const next = historyIndexRef.current - 1;
        if (next < 0) {
          setInput("");
          historyIndexRef.current = -1;
        } else if (history[next]) {
          setInput(history[next]);
          historyIndexRef.current = next;
        }
      }
    },
    [input, sendMessage, history],
  );

  const getRoleStyle = (role: ChatMessage["role"]): { color: string; prefix: string } => {
    switch (role) {
      case "user":
        return { color: "var(--prompt)", prefix: "> " };
      case "assistant":
        return { color: "var(--text-primary)", prefix: "" };
      case "system":
        return { color: "var(--system)", prefix: "[system] " };
      case "tool_call":
        return { color: "var(--tool-call)", prefix: "[tool] " };
      case "tool_result":
        return { color: "var(--tool-result)", prefix: "[result] " };
      case "cypher_result":
        return { color: "var(--node-function)", prefix: "" };
      case "cli_result":
        return { color: "var(--text-secondary)", prefix: "" };
    }
  };

  // Build prompt prefix showing current location
  const promptPath = breadcrumb.length > 1
    ? breadcrumb.map((b) => b.label).join("/")
    : "/";

  return (
    <div
      className="flex flex-col h-full"
      style={{ background: "var(--bg-secondary)" }}
    >
      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-3 space-y-1"
      >
        {messages.length === 0 && (
          <div
            className="text-xs font-mono"
            style={{ color: "var(--text-muted)" }}
          >
            <div>Navigate the graph like a filesystem. Type <span style={{ color: "var(--prompt)" }}>help</span> for commands.</div>
            <div style={{ marginTop: 4 }}>
              <span style={{ color: "var(--text-secondary)" }}>ls</span> / <span style={{ color: "var(--text-secondary)" }}>cd</span> / <span style={{ color: "var(--text-secondary)" }}>tree</span> — walk the graph
            </div>
            <div>
              <span style={{ color: "var(--node-function)" }}>MATCH ...</span> — Cypher queries
            </div>
            <div>
              <span style={{ color: "var(--prompt)" }}>? what calls save_order</span> — ask the LLM
            </div>
            <div>
              <span style={{ color: "var(--prompt)" }}>vfs? what does register_user call</span> — LLM query + VFS projection
            </div>
          </div>
        )}
        {messages.map((msg) => {
          const style = getRoleStyle(msg.role);
          return (
            <div
              key={msg.id}
              className="text-xs font-mono whitespace-pre-wrap break-words"
              style={{ color: style.color }}
            >
              <span style={{ opacity: 0.7 }}>{style.prefix}</span>
              {msg.content}
              {msg.role === "assistant" && isStreaming && msg.content === "" && (
                <span
                  className="inline-block w-2 h-3 ml-0.5"
                  style={{
                    background: "var(--prompt)",
                    animation: "pulse 1s ease-in-out infinite",
                  }}
                />
              )}
            </div>
          );
        })}
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex items-center border-t px-3 py-2 gap-2 flex-shrink-0"
        style={{ borderColor: "var(--border)" }}
      >
        {(() => {
          const m = input.trim() ? inputMode(input) : null;
          const modeColors: Record<string, string> = {
            cypher: "var(--node-function)",
            cypher_vfs: "var(--node-function)",
            nl: "var(--prompt)",
            nl_vfs: "var(--prompt)",
          };
          const promptColor = (m && modeColors[m]) || "var(--prompt)";
          const inputColor = (m && modeColors[m]) || "var(--text-primary)";
          return (
            <>
              <span className="text-xs font-mono flex-shrink-0" style={{ color: promptColor }}>
                {promptPath}&gt;
              </span>
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder={isStreaming ? "Running..." : "ls, cd, tree, MATCH ..., ? ask, vfs? ask"}
                disabled={isStreaming}
                className="flex-1 text-xs font-mono outline-none bg-transparent"
                style={{ color: inputColor }}
              />
            </>
          );
        })()}
        <button
          type="submit"
          disabled={isStreaming || !input.trim()}
          style={{
            background: "none",
            border: "none",
            cursor: isStreaming || !input.trim() ? "not-allowed" : "pointer",
            color: isStreaming || !input.trim() ? "var(--text-muted)" : "var(--prompt)",
          }}
        >
          <Send size={14} />
        </button>
      </form>
    </div>
  );
}

export default TerminalChat;
