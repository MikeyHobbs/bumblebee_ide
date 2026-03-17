import { useQuery } from "@tanstack/react-query";
import type { GraphNode, GraphEdge, LogicPack } from "@/types/graph";
import { apiFetch } from "./client";

interface GraphNodesResponse {
  nodes: GraphNode[];
  total: number;
}

export function useGraphNodes(
  label?: string,
  limit = 100,
  offset = 0,
  refetchInterval?: number | false,
) {
  return useQuery({
    queryKey: ["graph-nodes", label, limit, offset],
    queryFn: async (): Promise<GraphNodesResponse> => {
      const params = new URLSearchParams();
      if (label) params.set("label", label);
      params.set("limit", String(limit));
      params.set("offset", String(offset));
      const nodes = await apiFetch<GraphNode[]>(
        `/api/v1/graph/nodes?${params.toString()}`,
      );
      return { nodes, total: nodes.length };
    },
    refetchInterval: refetchInterval ?? false,
  });
}

export function useGraphNode(nodeId: string | null) {
  return useQuery({
    queryKey: ["graph-node", nodeId],
    queryFn: () => apiFetch<GraphNode>(`/api/v1/graph/node/${nodeId}`),
    enabled: nodeId !== null,
  });
}

interface SubgraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export function useModuleGraph(refetchInterval?: number | false) {
  return useQuery({
    queryKey: ["module-graph"],
    queryFn: () => apiFetch<SubgraphResponse>("/api/v1/graph/modules"),
    refetchInterval: refetchInterval ?? false,
  });
}

export function useFileMembers(modulePath: string | null) {
  return useQuery({
    queryKey: ["file-members", modulePath],
    queryFn: () =>
      apiFetch<SubgraphResponse>(
        `/api/v1/graph/file-members/${modulePath!}`,
      ),
    enabled: modulePath !== null,
  });
}

export interface OverviewNode { id: string; kind: string; name: string; module_path: string; }
export interface OverviewEdge { type: string; source: string; target: string; }

export function useGraphOverview() {
  return useQuery({
    queryKey: ["graph-overview"],
    queryFn: () => apiFetch<{ nodes: OverviewNode[]; edges: OverviewEdge[] }>("/api/v1/graph-overview"),
    staleTime: 30_000,
  });
}

export function useGraphHasData() {
  return useQuery({
    queryKey: ["logic-nodes-probe"],
    queryFn: () => apiFetch<Array<{ id: string }>>("/api/v1/nodes?limit=1"),
    staleTime: 30_000,
  });
}

export function useLogicPack(
  nodeId: string | null,
  type = "full",
  hops = 2,
) {
  return useQuery({
    queryKey: ["logic-pack", nodeId, type, hops],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("type", type);
      params.set("hops", String(hops));
      return apiFetch<LogicPack>(
        `/api/v1/logic-pack/${nodeId}?${params.toString()}`,
      );
    },
    enabled: nodeId !== null,
  });
}

export function useFunctionDetail(functionName: string | null) {
  return useQuery({
    queryKey: ["function-detail", functionName],
    queryFn: () =>
      apiFetch<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
        `/api/v1/graph/function/${encodeURIComponent(functionName!)}`,
      ),
    enabled: functionName !== null,
  });
}

export function useFunctionControlFlow(functionName: string | null) {
  return useQuery({
    queryKey: ["function-control-flow", functionName],
    queryFn: () =>
      apiFetch<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
        `/api/v1/graph/function/${encodeURIComponent(functionName!)}?include_flow=true`,
      ),
    enabled: functionName !== null,
  });
}

export function useClassDetail(className: string | null) {
  return useQuery({
    queryKey: ["class-detail", className],
    queryFn: () =>
      apiFetch<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
        `/api/v1/graph/class/${encodeURIComponent(className!)}`,
      ),
    enabled: className !== null,
  });
}

export function useAllEdges() {
  return useQuery({
    queryKey: ["all-edges"],
    queryFn: () =>
      apiFetch<Array<{ type: string; source: string; target: string; properties: Record<string, unknown> }>>(
        "/api/v1/edges/all?limit=5000",
      ),
  });
}
