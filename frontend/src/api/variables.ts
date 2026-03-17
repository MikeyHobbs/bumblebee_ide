import { useQuery } from "@tanstack/react-query";
import type {
  GraphEdge,
  GraphNode,
  MutationTimeline,
  VariableSearchResult,
} from "@/types/graph";
import { apiFetch } from "./client";

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

export function useVariableDetail(variableName: string | null) {
  return useQuery({
    queryKey: ["variable-detail", variableName],
    queryFn: () =>
      apiFetch<{ nodes: GraphNode[]; edges: GraphEdge[] }>(
        `/api/v1/graph/variable/${encodeURIComponent(variableName!)}`,
      ),
    enabled: variableName !== null,
  });
}
