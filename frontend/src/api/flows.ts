import { useQuery } from "@tanstack/react-query";
import { apiFetch, type LogicNodeResponse } from "./client";

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
