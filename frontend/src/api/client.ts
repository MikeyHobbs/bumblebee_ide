export async function apiFetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, init);
  if (!res.ok) {
    const text = await res.text().catch(() => "Unknown error");
    throw new Error(`API ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const WS_URL = `ws://${window.location.hostname}:8111/api/v1/ws`;

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

// Re-export all hooks from domain modules for convenience
export { useGraphNodes, useGraphNode, useModuleGraph, useFileMembers, useGraphOverview, useGraphHasData, useAllEdges, useLogicPack, useFunctionDetail, useFunctionControlFlow, useClassDetail } from "./graph";
export type { OverviewNode, OverviewEdge } from "./graph";
export { useLogicNodes, useLogicNode, useNodeEdges, useNodeVariables } from "./nodes";
export type { NodeVariable } from "./nodes";
export { useVariableTimeline, useVariableSearch, useVariableDetail } from "./variables";
export { useFlows, useFlow, useGapReport } from "./flows";
export { useIndexRepository, useImportDirectory, useSemanticDiff } from "./import";
export { useFileContent } from "./files";
export { useCypherCompare, useRateEval, useEvalHistory, useEvalStats } from "./cypherEval";
export type { CompareResponse, ModelResult, EvalStats } from "./cypherEval";
