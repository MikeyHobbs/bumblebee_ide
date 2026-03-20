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

export interface ConsumerNode {
  id: string;
  name: string;
  kind: string;
  module_path: string;
  signature: string;
  confidence: "exact" | "structural" | "weak";
}

export interface TypeShapeNode {
  id: string;
  base_type: string;
  definition: string;
}

export interface ConsumerSubgraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface ConsumerSubgraph {
  type_shapes: TypeShapeNode[];
  consumers: ConsumerNode[];
  edges: ConsumerSubgraphEdge[];
}

export interface TypeShapeDetail {
  id: string;
  shape_hash: string;
  kind: string;
  base_type: string;
  definition: Record<string, unknown>;
  created_at: string;
  connections: {
    variables: Array<{ id: string; name: string; type_hint: string | null }>;
    accepting_functions: Array<{ id: string; name: string; kind: string; module_path: string; signature: string }>;
    producing_functions: Array<{ id: string; name: string; kind: string; module_path: string }>;
    compatible_shapes: Array<{ id: string; base_type: string }>;
  };
}

export function useTypeShapeDetail(shapeId: string | null) {
  return useQuery({
    queryKey: ["type-shape-detail", shapeId],
    queryFn: () => apiFetch<TypeShapeDetail>(`/api/v1/type-shapes/detail/${shapeId!}`),
    enabled: shapeId !== null,
  });
}

export function useConsumerSubgraph(variableId: string | null) {
  return useQuery({
    queryKey: ["consumer-subgraph", variableId],
    queryFn: () => apiFetch<ConsumerSubgraph>(`/api/v1/type-shapes/${variableId!}/consumer-subgraph`),
    enabled: variableId !== null,
  });
}
