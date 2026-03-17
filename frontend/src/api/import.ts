import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch, type LogicNodeResponse } from "./client";

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
    enabled: false,
  });
}
