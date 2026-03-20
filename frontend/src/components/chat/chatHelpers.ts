import type { CypherQueryResponse, AnyNode } from "./chatTypes";

export function formatCypherResults(data: CypherQueryResponse): string {
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

export function localName(qualifiedName: string): string {
  const parts = qualifiedName.split(".");
  return parts[parts.length - 1] ?? qualifiedName;
}

/** Format a single node for ls/tree output. */
export function formatNodeLine(n: AnyNode, indent = ""): string {
  const line = typeof n.properties["start_line"] === "number" ? `:${n.properties["start_line"]}` : "";
  const label = n.label;
  const name = localName(n.id);
  return `${indent}[${label}] ${name}${line}`;
}

/** Fetch JSON helper. */
export async function fetchJson<T>(url: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(url, init);
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}
