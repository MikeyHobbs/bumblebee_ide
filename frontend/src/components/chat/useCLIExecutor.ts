import { useCallback } from "react";
import type { ChatMessage, CypherQueryResponse, SubgraphResponse } from "./chatTypes";
import { localName, formatNodeLine, fetchJson } from "./chatHelpers";

interface CLIExecutorDeps {
  addMsg: (role: ChatMessage["role"], content: string) => void;
  breadcrumb: Array<{ label: string; nodeId: string | null }>;
  viewMode: string;
  activeNodeId: string | null;
  navigateBack: (index: number) => void;
  goHome: () => void;
  navigateToNode: (id: string, label: string) => void;
}

export function useCLIExecutor({
  addMsg,
  breadcrumb,
  viewMode,
  activeNodeId,
  navigateBack,
  goHome,
  navigateToNode,
}: CLIExecutorDeps) {
  /** Fetch children of the current graph position. */
  const fetchCurrentChildren = useCallback(async (): Promise<SubgraphResponse | null> => {
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
  }, [viewMode, activeNodeId]);

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
    [breadcrumb, viewMode, activeNodeId, navigateBack, goHome, navigateToNode, addMsg, fetchCurrentChildren],
  );

  return { executeCli, fetchCurrentChildren };
}
