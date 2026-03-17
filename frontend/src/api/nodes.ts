import { useQuery } from "@tanstack/react-query";
import { apiFetch, type LogicNodeResponse } from "./client";

export function useLogicNodes(query?: string, kind?: string, limit = 100) {
  return useQuery({
    queryKey: ["logic-nodes", query, kind, limit],
    queryFn: () => {
      const params = new URLSearchParams();
      if (query) params.set("query", query);
      if (kind) params.set("kind", kind);
      params.set("limit", String(limit));
      return apiFetch<LogicNodeResponse[]>(`/api/v1/nodes?${params.toString()}`);
    },
  });
}

export function useLogicNode(nodeId: string | null) {
  return useQuery({
    queryKey: ["logic-node", nodeId],
    queryFn: () => apiFetch<LogicNodeResponse>(`/api/v1/nodes/${nodeId!}`),
    enabled: nodeId !== null,
  });
}

export function useNodeEdges(
  nodeId: string | null,
  direction = "outgoing",
  types?: string[],
) {
  return useQuery({
    queryKey: ["node-edges", nodeId, direction, types],
    queryFn: () => {
      const params = new URLSearchParams({ direction });
      if (types?.length) params.set("types", types.join(","));
      return apiFetch<Array<{ type: string; source: string; target: string; properties: Record<string, unknown> }>>(
        `/api/v1/nodes/${nodeId!}/edges?${params.toString()}`,
      );
    },
    enabled: nodeId !== null,
  });
}

export interface NodeVariable {
  id: string;
  name: string;
  type_hint: string | null;
  is_parameter: boolean;
  is_attribute: boolean;
  edge_type: string;
}

export function useNodeVariables(nodeId: string | null) {
  return useQuery({
    queryKey: ["node-variables", nodeId],
    queryFn: () => apiFetch<NodeVariable[]>(`/api/v1/nodes/${nodeId!}/variables`),
    enabled: nodeId !== null,
  });
}
