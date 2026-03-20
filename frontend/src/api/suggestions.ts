/**
 * Imperative fetch for graph-aware autocomplete suggestions.
 *
 * These are NOT hooks — Monaco's provideCompletionItems is a callback,
 * not a React component. Use plain async functions here.
 */

import { apiFetch } from "./client";

export interface GraphCompletionItem {
  label: string;
  kind: string; // "function" | "method" | "class"
  detail: string; // signature
  documentation: string;
  insert_text: string; // snippet with ${1:param} placeholders
  sort_key: string;
  node_id: string;
  module_path: string;
}

interface CompletionRequest {
  trigger: string;
  variable_name?: string;
  type_hint?: string;
  object_name?: string;
  module_prefix?: string;
  query?: string;
  scope_node_ids?: string[];
  limit?: number;
}

export async function fetchCompletions(
  trigger: string,
  params: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<GraphCompletionItem[]> {
  const body: CompletionRequest = { trigger, ...params };
  return apiFetch<GraphCompletionItem[]>("/api/v1/suggestions/complete", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal: signal ?? null,
  });
}
