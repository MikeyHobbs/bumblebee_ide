import {
  useQuery,
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";
import type {
  GraphNode,
  GraphEdge,
  LogicPack,
  MutationTimeline,
  VariableSearchResult,
} from "@/types/graph";

export async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
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

interface IndexJobResponse {
  job_id: string;
  status: string;
}

export function useIndexRepository() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (repoPath: string): Promise<IndexJobResponse> => {
      const res = await fetch("/api/v1/index", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: repoPath }),
      });
      if (!res.ok) {
        const text = await res.text().catch(() => "Unknown error");
        throw new Error(`API ${res.status}: ${text}`);
      }
      return res.json() as Promise<IndexJobResponse>;
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["graph-nodes"] });
    },
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

export function useFunctionDetail(functionName: string | null) {
  return useQuery({
    queryKey: ["function-detail", functionName],
    queryFn: () =>
      apiFetch<SubgraphResponse>(
        `/api/v1/graph/function/${encodeURIComponent(functionName!)}`,
      ),
    enabled: functionName !== null,
  });
}

export function useFunctionControlFlow(functionName: string | null) {
  return useQuery({
    queryKey: ["function-control-flow", functionName],
    queryFn: () =>
      apiFetch<SubgraphResponse>(
        `/api/v1/graph/function/${encodeURIComponent(functionName!)}?include_flow=true`,
      ),
    enabled: functionName !== null,
  });
}

export function useClassDetail(className: string | null) {
  return useQuery({
    queryKey: ["class-detail", className],
    queryFn: () =>
      apiFetch<SubgraphResponse>(
        `/api/v1/graph/class/${encodeURIComponent(className!)}`,
      ),
    enabled: className !== null,
  });
}

export function useVariableDetail(variableName: string | null) {
  return useQuery({
    queryKey: ["variable-detail", variableName],
    queryFn: () =>
      apiFetch<SubgraphResponse>(
        `/api/v1/graph/variable/${encodeURIComponent(variableName!)}`,
      ),
    enabled: variableName !== null,
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

// --- 800-series API hooks ---

export interface LogicNodeResponse {
  id: string;
  ast_hash: string;
  kind: string;
  name: string;
  module_path: string;
  signature: string;
  source_text: string;
  semantic_intent: string | null;
  docstring: string | null;
  params: Array<{ name: string; type_hint: string | null }>;
  return_type: string | null;
  tags: string[];
  status: string;
  start_line: number | null;
  end_line: number | null;
  created_at: string;
  updated_at: string;
}

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

/** Quick check if graph already has indexed data. */
export function useGraphHasData() {
  return useQuery({
    queryKey: ["logic-nodes-probe"],
    queryFn: () => apiFetch<LogicNodeResponse[]>("/api/v1/nodes?limit=1"),
    staleTime: 30_000,
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

export function useAllEdges() {
  return useQuery({
    queryKey: ["all-edges"],
    queryFn: () =>
      apiFetch<Array<{ type: string; source: string; target: string; properties: Record<string, unknown> }>>(
        "/api/v1/edges/all?limit=5000",
      ),
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

export function useImportDirectory() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (dirPath: string) => {
      return apiFetch<{ nodes_created: number; edges_created: number; files_processed: number }>(
        "/api/v1/import/directory",
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ path: dirPath }),
        },
      );
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["logic-nodes"] });
      void queryClient.invalidateQueries({ queryKey: ["all-edges"] });
      void queryClient.invalidateQueries({ queryKey: ["graph-overview"] });
    },
  });
}

export function useFlows() {
  return useQuery({
    queryKey: ["flows"],
    queryFn: () =>
      apiFetch<Array<{ id: string; name: string; description: string | null; node_ids: string[]; entry_point: string }>>(
        "/api/v1/flows",
      ),
  });
}

export function useFlow(flowId: string | null) {
  return useQuery({
    queryKey: ["flow", flowId],
    queryFn: () =>
      apiFetch<{ id: string; name: string; description: string | null; node_ids: string[]; entry_point: string }>(
        `/api/v1/flows/${flowId!}`,
      ),
    enabled: flowId !== null,
  });
}

export function useGapReport(scope?: string) {
  return useQuery({
    queryKey: ["gap-report", scope],
    queryFn: () => {
      const params = scope ? `?scope=${encodeURIComponent(scope)}` : "";
      return apiFetch<{ dead_ends: LogicNodeResponse[]; orphans: LogicNodeResponse[]; circular_deps: string[][] }>(
        `/api/v1/flows/gaps${params}`,
      );
    },
  });
}

export function useSemanticDiff(path?: string) {
  return useQuery({
    queryKey: ["semantic-diff", path],
    queryFn: () =>
      apiFetch<{
        added_nodes: LogicNodeResponse[];
        removed_nodes: LogicNodeResponse[];
        modified_nodes: Array<{ id: string; old_ast_hash: string; new_ast_hash: string }>;
        added_edges: Array<{ type: string; source: string; target: string }>;
        removed_edges: Array<{ type: string; source: string; target: string }>;
      }>(`/api/v1/import/diff${path ? `?path=${encodeURIComponent(path)}` : ""}`),
    enabled: false, // Only fetch on demand
  });
}
