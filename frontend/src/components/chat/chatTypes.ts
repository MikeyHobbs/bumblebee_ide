import type { GraphNode, GraphEdge } from "@/types/graph";
import type { SubgraphResponse } from "@/api/graph";

export interface ChatMessage {
  id: string;
  role: "user" | "assistant" | "system" | "tool_call" | "tool_result" | "cypher_result" | "cli_result";
  content: string;
  timestamp: number;
}

export interface CypherNode {
  id: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface CypherEdge {
  type: string;
  source: string;
  target: string;
  properties: Record<string, unknown>;
}

export interface CypherQueryResponse {
  nodes: CypherNode[];
  edges: CypherEdge[];
  raw_results: Array<Array<string | number | null>>;
}

/** A node from either the raw query or subgraph endpoint. */
export type AnyNode = CypherNode | GraphNode;

export type { SubgraphResponse, GraphNode, GraphEdge };
