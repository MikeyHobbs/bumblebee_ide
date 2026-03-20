import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { apiFetch } from "./client";

// --- Types ---

export interface ModelResult {
  model: string;
  cypher: string;
  results: Record<string, unknown>[];
  row_count: number;
  latency_ms: number;
  error: string | null;
}

export interface CompareResponse {
  eval_id: string;
  question: string;
  model_a: ModelResult;
  model_b: ModelResult;
}

export interface RateResponse {
  eval_id: string;
  winner: string;
  notes: string;
}

export interface EvalHistoryResponse {
  items: Array<{
    eval_id: string;
    question: string;
    model_a: ModelResult;
    model_b: ModelResult;
    rating: { winner: string; notes: string } | null;
  }>;
  total: number;
}

export interface EvalStats {
  total: number;
  rated: number;
  wins: Record<string, number>;
}

// --- Hooks ---

export function useCypherCompare() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { question: string; model_a: string; model_b: string }) =>
      apiFetch<CompareResponse>("/api/v1/cypher-eval/compare", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cypher-eval-history"] });
      void qc.invalidateQueries({ queryKey: ["cypher-eval-stats"] });
    },
  });
}

export function useRateEval() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { eval_id: string; winner: string; notes: string }) =>
      apiFetch<RateResponse>("/api/v1/cypher-eval/rate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["cypher-eval-history"] });
      void qc.invalidateQueries({ queryKey: ["cypher-eval-stats"] });
    },
  });
}

export function useEvalHistory(limit = 50, offset = 0) {
  return useQuery({
    queryKey: ["cypher-eval-history", limit, offset],
    queryFn: () =>
      apiFetch<EvalHistoryResponse>(
        `/api/v1/cypher-eval/history?limit=${limit}&offset=${offset}`,
      ),
  });
}

export function useEvalStats() {
  return useQuery({
    queryKey: ["cypher-eval-stats"],
    queryFn: () => apiFetch<EvalStats>("/api/v1/cypher-eval/stats"),
  });
}
