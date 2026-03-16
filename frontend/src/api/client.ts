import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import type {
  GraphNode,
  LogicPack,
  MutationTimeline,
  VariableSearchResult,
} from "@/types/graph";

async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

interface GraphNodesResponse {
  nodes: GraphNode[];
  total: number;
}

export function useGraphNodes(
  label?: string,
  limit = 100,
  offset = 0,
) {
  return useQuery({
    queryKey: ["graph-nodes", label, limit, offset],
    queryFn: () => {
      const params = new URLSearchParams();
      if (label) params.set("label", label);
      params.set("limit", String(limit));
      params.set("offset", String(offset));
      return apiFetch<GraphNodesResponse>(
        `/api/v1/graph/nodes?${params.toString()}`,
      );
    },
  });
}

export function useGraphNode(nodeId: string | null) {
  return useQuery({
    queryKey: ["graph-node", nodeId],
    queryFn: () => apiFetch<GraphNode>(`/api/v1/graph/node/${nodeId}`),
    enabled: nodeId !== null,
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

export function useVariableTimeline(variableId: string | null) {
  return useQuery({
    queryKey: ["variable-timeline", variableId],
    queryFn: () =>
      apiFetch<MutationTimeline>(
        `/api/v1/variables/${variableId}/timeline`,
      ),
    enabled: variableId !== null,
  });
}

export function useVariableSearch(name: string, scope?: string) {
  return useQuery({
    queryKey: ["variable-search", name, scope],
    queryFn: () => {
      const params = new URLSearchParams();
      params.set("name", name);
      if (scope) params.set("scope", scope);
      return apiFetch<VariableSearchResult[]>(
        `/api/v1/variables/search?${params.toString()}`,
      );
    },
    enabled: name.length > 0,
  });
}

interface IndexResponse {
  status: string;
  nodes_created: number;
  edges_created: number;
}

export function useIndexRepository() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (repoPath: string) =>
      apiFetch<IndexResponse>("/api/v1/index", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: repoPath }),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["graph-nodes"] });
    },
  });
}

export function useFileContent(path: string | null) {
  return useQuery({
    queryKey: ["file-content", path],
    queryFn: () =>
      apiFetch<{ content: string; language: string }>(
        `/api/v1/file?path=${encodeURIComponent(path!)}`,
      ),
    enabled: path !== null,
  });
}
